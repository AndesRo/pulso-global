import monitor_indicadores as m


def test_sma():
    assert m.sma([1, 2, 3, 4, 5], 3) == 4


def test_zscore_detecta_salto():
    base = [100 + (i % 2) * 0.1 for i in range(40)]
    assert abs(m.zscore_ultimo_retorno(base + [110])) > m.UMBRAL_ZSCORE


def test_zscore_serie_plana():
    assert m.zscore_ultimo_retorno([100.0] * 40) == 0.0


def test_alerta_variacion_diaria():
    serie = m.simular_serie("dolar")
    r = m.analizar("dolar", serie, "simulado")
    assert any("Variación diaria" in a for a in r.alertas)


def test_sin_alertas_en_indicador_estable():
    r = m.analizar("uf", m.simular_serie("uf"), "simulado")
    assert not any("Variación diaria" in a for a in r.alertas)


def test_simulacion_reproducible():
    assert m.simular_serie("euro") == m.simular_serie("euro")


def test_html_contiene_indicadores():
    rs = [m.analizar(c, m.simular_serie(c), "simulado") for c in m.INDICADORES]
    html = m.generar_html(rs)
    assert "Dólar observado" in html and "alertas activas" in html