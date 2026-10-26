from archivist_app.services import notifier


def preparar(monkeypatch, reloj):
    mostrados, dormidos = [], []
    monkeypatch.setattr(notifier, "_ultimo", None)
    monkeypatch.setattr(notifier, "_mostrar", lambda t, m, d: mostrados.append((t, m, d)))
    monkeypatch.setattr(notifier.time, "monotonic", lambda: reloj[0])
    monkeypatch.setattr(notifier.time, "sleep", lambda s: (dormidos.append(s), reloj.__setitem__(0, reloj[0] + s)))
    return mostrados, dormidos


def test_el_primer_aviso_no_espera(monkeypatch):
    mostrados, dormidos = preparar(monkeypatch, [100.0])
    notifier.notificar("t", "m", "long")
    assert mostrados == [("t", "m", "long")] and dormidos == []


def test_dos_avisos_seguidos_se_separan(monkeypatch):
    mostrados, dormidos = preparar(monkeypatch, [100.0])
    notifier.notificar("a", "1")
    notifier.notificar("b", "2")
    assert [m[0] for m in mostrados] == ["a", "b"]
    assert dormidos == [notifier.SEPARACION_S]


def test_si_ya_paso_el_tiempo_no_espera(monkeypatch):
    reloj = [100.0]
    mostrados, dormidos = preparar(monkeypatch, reloj)
    notifier.notificar("a", "1")
    reloj[0] += notifier.SEPARACION_S + 1
    notifier.notificar("b", "2")
    assert len(mostrados) == 2 and dormidos == []


def test_un_aviso_que_falla_no_lanza_excepcion(monkeypatch):
    preparar(monkeypatch, [100.0])

    def falla(*a):
        raise OSError("sin shell de notificaciones")

    monkeypatch.setattr(notifier, "_mostrar", falla)
    notifier.notificar("t", "m")  # no debe propagar