"""Alineamiento determinista de palabras, sin interpretar diferencias como errores."""
from difflib import SequenceMatcher
import re


def compare_texts(left, right):
    # Conservamos espacios y saltos para que el usuario vea el texto original.
    a = re.findall(r'\s+|[^\s]+', left or '')
    b = re.findall(r'\s+|[^\s]+', right or '')
    matcher = SequenceMatcher(a=a, b=b, autojunk=False)
    chunks = []
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag != 'equal' and not ''.join(a[i:j]).strip() and not ''.join(b[k:l]).strip():
            tag = 'equal'  # los saltos de párrafo pueden diferir sin cambiar palabras
        first, second = ''.join(a[i:j]), ''.join(b[k:l])
        attention = None
        if tag != 'equal':
            combined = first + ' ' + second
            if re.search(r'\d|\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b', combined, re.I):
                attention = 'cifras o fechas'
            elif re.search(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b', combined):
                attention = 'posible nombre propio'
        chunks.append({'kind': tag, 'kraken': first, 'second': second, 'attention': attention})
    return {'chunks': chunks, 'differences': sum(c['kind'] != 'equal' for c in chunks)}
