"""Modelos del listado de comprobantes recibidos. Lógica pura: sin Playwright ni portal.

Todo lo que se puede comprobar sin el portal se comprueba aquí. Reglas verificadas con las
18 filas reales de un listado: el dígito verificador de la clave (18/18), que su RUC y su
número coinciden con los de la fila (18/18) y que su fecha coincide con "Fecha emisión" (18/18).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

# Código de tipo DENTRO de la clave de acceso. Observado con datos reales solo "07"; el resto
# sale de la ficha técnica del SRI y no se ha visto en este portal.
TIPOS = {
    "01": "Factura",
    "03": "Liquidación de compra",
    "04": "Nota de crédito",
    "05": "Nota de débito",
    "06": "Guía de remisión",
    "07": "Comprobante de retención",
}

# Valor del combo "Tipo de comprobante" del portal -> código dentro de la clave.
# Verificado con datos reales solo "6" -> "07".
TIPO_PORTAL_A_CODIGO = {"1": "01", "2": "03", "3": "04", "4": "05", "6": "07"}

_PESOS = (2, 3, 4, 5, 6, 7)
_RE_CLAVE = re.compile(r"[0-9]{49}")
_RE_NUMERO = re.compile(r"([0-9]{3}-[0-9]{3}-[0-9]{9})$")
_RE_RUC_RAZON = re.compile(r"([0-9]{13}) (.+)")
_RE_FECHA = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4}")
_RE_FECHA_HORA = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}")


def digito_verificador(primeros_48: str) -> int:
    """Módulo 11, pesos 2 a 7 repetidos de derecha a izquierda; 11 -> 0 y 10 -> 1."""
    suma = sum(int(d) * _PESOS[i % 6] for i, d in enumerate(reversed(primeros_48)))
    resto = 11 - (suma % 11)
    return {11: 0, 10: 1}.get(resto, resto)


def parse_fecha(texto: str) -> date:
    limpio = (texto or "").strip()
    if not _RE_FECHA.fullmatch(limpio):
        raise ValueError("Fecha con formato inesperado (se esperaba dd/mm/aaaa)")
    return datetime.strptime(limpio, "%d/%m/%Y").date()


def parse_fecha_hora(texto: str) -> datetime:
    limpio = (texto or "").strip()
    if not _RE_FECHA_HORA.fullmatch(limpio):
        raise ValueError("Fecha y hora con formato inesperado (se esperaba dd/mm/aaaa hh:mm:ss)")
    return datetime.strptime(limpio, "%d/%m/%Y %H:%M:%S")


@dataclass(frozen=True)
class ClaveAcceso:
    valor: str
    fecha_emision: date
    codigo_tipo: str
    ruc_emisor: str
    ambiente: str
    establecimiento: str
    punto_emision: str
    secuencial: str

    @classmethod
    def parse(cls, texto: str) -> "ClaveAcceso":
        # Los mensajes no repiten la clave: es un dato del negocio.
        v = (texto or "").strip()
        if not _RE_CLAVE.fullmatch(v):
            raise ValueError("La clave de acceso debe tener exactamente 49 dígitos")
        if digito_verificador(v[:48]) != int(v[48]):
            raise ValueError("La clave de acceso tiene un dígito verificador inválido")
        try:
            fecha = date(int(v[4:8]), int(v[2:4]), int(v[0:2]))
        except ValueError:
            raise ValueError("La fecha dentro de la clave de acceso no es válida") from None
        return cls(
            valor=v,
            fecha_emision=fecha,
            codigo_tipo=v[8:10],
            ruc_emisor=v[10:23],
            ambiente=v[23],
            establecimiento=v[24:27],
            punto_emision=v[27:30],
            secuencial=v[30:39],
        )

    @property
    def numero(self) -> str:
        return f"{self.establecimiento}-{self.punto_emision}-{self.secuencial}"

    @property
    def tipo(self) -> str:
        return TIPOS.get(self.codigo_tipo, f"Tipo {self.codigo_tipo}")


@dataclass(frozen=True)
class Comprobante:
    nro: int
    clave: ClaveAcceso
    ruc_emisor: str
    razon_social_emisor: str
    fecha_emision: date
    fecha_autorizacion: datetime

    def __post_init__(self) -> None:
        if self.fecha_emision != self.clave.fecha_emision:
            raise ValueError("La fecha de emisión de la fila no coincide con la de su clave de acceso")
        if self.ruc_emisor != self.clave.ruc_emisor:
            raise ValueError("El RUC del emisor de la fila no coincide con el de su clave de acceso")

    @classmethod
    def desde_celdas(
        cls,
        nro: str,
        ruc_y_razon: str,
        tipo_y_serie: str,
        clave: str,
        fecha_autorizacion: str,
        fecha_emision: str,
    ) -> "Comprobante":
        """Construye un comprobante con el TEXTO de las celdas de una fila del listado."""
        if not re.fullmatch(r"[0-9]+", (nro or "").strip()):
            raise ValueError("El número de fila no es un entero")
        m = _RE_RUC_RAZON.fullmatch(" ".join((ruc_y_razon or "").split()))
        if not m:
            raise ValueError("La celda del emisor no trae un RUC de 13 dígitos y una razón social")
        clave_acceso = ClaveAcceso.parse(clave)
        n = _RE_NUMERO.search(" ".join((tipo_y_serie or "").split()))
        if not n or n.group(1) != clave_acceso.numero:
            raise ValueError("El número de la fila no coincide con el de su clave de acceso")
        return cls(
            nro=int(nro.strip()),
            clave=clave_acceso,
            ruc_emisor=m.group(1),
            razon_social_emisor=m.group(2),
            fecha_emision=parse_fecha(fecha_emision),
            fecha_autorizacion=parse_fecha_hora(fecha_autorizacion),
        )


def validar_lote(comprobantes: list[Comprobante], codigo_tipo_esperado: str | None = None) -> None:
    """Controles del listado completo. Un listado vacío es válido (consulta sin resultados)."""
    claves = [c.clave.valor for c in comprobantes]
    if len(set(claves)) != len(claves):
        raise ValueError("Hay claves de acceso repetidas en el listado")
    if codigo_tipo_esperado is not None:
        otros = {c.clave.codigo_tipo for c in comprobantes} - {codigo_tipo_esperado}
        if otros:
            raise ValueError("El listado trae comprobantes de un tipo distinto al solicitado")


def nros_contiguos(comprobantes: list[Comprobante]) -> bool:
    """Nro va de 1 a N sin saltos. HIPÓTESIS sin verificar: que continúe entre páginas
    (solo se ha visto una página)."""
    return [c.nro for c in comprobantes] == list(range(1, len(comprobantes) + 1))