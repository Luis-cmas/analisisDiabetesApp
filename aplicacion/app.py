import os
import pandas as pd
import sshtunnel
from dotenv import load_dotenv
from flask import Flask, render_template, request
from sqlalchemy import create_engine, text

# 1. Inicializar Flask
app = Flask(__name__)

# 2. Cargar variables de entorno desde el archivo .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Variables de la Base de Datos
usuario_bd = os.getenv("USUARIO")
pass_bd = os.getenv("PASSWORD")
host_bd = os.getenv("HOST")
nombre_bd = os.getenv("NOMBRE_BD")

# Variables para Túnel SSH (Solo para pruebas locales)
ssh_host = os.getenv("SSH_HOST", "ssh.pythonanywhere.com")
ssh_user = os.getenv("SSH_USER", usuario_bd)
ssh_pass = os.getenv("PASSWORDPA")  # Contraseña de tu cuenta de PythonAnywhere

# Variable global para el engine de SQLAlchemy
engine = None

# 3. Configurar la conexión a la base de datos según el entorno
if __name__ == '__main__':
    # ------------------------------------------------------------------
    # ENTORNO LOCAL: Abrir Túnel SSH antes de arrancar Flask
    # ------------------------------------------------------------------
    tunnel = sshtunnel.SSHTunnelForwarder(
        (ssh_host, 22),
        ssh_username=ssh_user,
        ssh_password=ssh_pass,
        remote_bind_address=(host_bd, 3306)
    )
    tunnel.start()

    cadena_conexion = f"mysql+pymysql://{usuario_bd}:{pass_bd}@127.0.0.1:{tunnel.local_bind_port}/{nombre_bd}"
    engine = create_engine(cadena_conexion,
                            pool_recycle=280,  # Recicla conexiones cada 280 segundos
                            pool_pre_ping=True  # Verifica si la conexión sigue viva antes de usarla
                            )
    print(f"-> Túnel SSH iniciado en el puerto local: {tunnel.local_bind_port}")
else:
    # ------------------------------------------------------------------
    # ENTORNO PRODUCCIÓN: Conexión directa
    # ------------------------------------------------------------------
    cadena_conexion = f"mysql+pymysql://{usuario_bd}:{pass_bd}@{host_bd}/{nombre_bd}"
    engine = create_engine(cadena_conexion,
                                pool_recycle=280,  # Recicla conexiones cada 280 segundos
                                pool_pre_ping=True  # Verifica si la conexión sigue viva antes de usarla
                                )


# --- RUTAS DE FLASK ---

@app.route('/')
def index():
    return render_template("index.html")


@app.route('/consulta/')
def consulta():
    return render_template("consultas.html")

@app.route('/tutorial/')
def tutorial():
    return render_template("tutorial.html")

########################################################################################################################
@app.route('/consultar', methods=['POST'])
def consultar():
    # 1. Obtenemos la lista de alcaldías seleccionadas y los periodos
    alcaldias = request.form.getlist('alcaldia[]')
    p_inicio = int(request.form.get('periodo_inicio'))
    p_fin = int(request.form.get('periodo_fin'))
    parametro = request.form.get('parametro')

    # Garantizamos que el periodo inicio sea menor o igual al periodo fin
    periodo_min = min(p_inicio, p_fin)
    periodo_max = max(p_inicio, p_fin)
    if periodo_max == periodo_min:
        return render_template(
            'consultas.html',
            error="Por favor seleccione un periodo más largo."
        )

    if not alcaldias:
        return "Por favor selecciona al menos una alcaldía.", 400

    # 2. Construcción dinámica de la consulta SQL según el parámetro seleccionado
    if parametro == 'mortalidad':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                a.habitantes,
                COUNT(p.dmt) AS total_casos
            FROM Paciente p
            JOIN Alcaldia a ON p.clave_municipio = a.id_alcaldia AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo
            ORDER BY p.periodo ASC, a.nombre ASC;
        """)
        print('se realizo la consulta de mortaliad')#revisada
        # Ejecutar consulta
        with engine.connect() as conn:
            df_resultado = pd.read_sql(
                query,
                con=conn,
                params={
                    'alcaldias': tuple(alcaldias),
                    'p_min': periodo_min,
                    'p_max': periodo_max,
                },
            )

        # Si el parámetro es mortalidad, calculamos la tasa y estructuramos para Chart.js
        datos_grafica = None

        if parametro == 'mortalidad' and not df_resultado.empty:
            # Cálculo de la tasa por 100k habitantes
            df_resultado['tasa_100k'] = (df_resultado['total_casos'] / df_resultado['habitantes']) * 100000
            df_resultado['tasa_100k'] = df_resultado['tasa_100k'].round(2)
            
            # Obtener periodos únicos para el Eje X (ordenados)
            periodos_eje_x = sorted(df_resultado['periodo'].unique().tolist())
            
            # Estructurar datasets para Chart.js (una línea por cada alcaldía)
            datasets = []
            
            # Generador de colores simples
            colores = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6610f2', '#fd7e14']
            
            for i, alcaldia in enumerate(df_resultado['alcaldia'].unique()):
                df_alc = df_resultado[df_resultado['alcaldia'] == alcaldia]
                
                # Mapear las tasas asegurando que coincidan con los periodos del Eje X
                tasas_map = dict(zip(df_alc['periodo'], df_alc['tasa_100k']))
                datos_serie = [tasas_map.get(p, None) for p in periodos_eje_x]
                
                color = colores[i % len(colores)]
                
                datasets.append({
                    'label': alcaldia,
                    'data': datos_serie,
                    'borderColor': color,
                    'backgroundColor': color,
                    'borderWidth': 2,
                    'fill': False,
                    'tension': 0.2
                })
                
            datos_grafica = {
                'periodos': periodos_eje_x,
                'datasets': datasets
            }

        # Convertir a diccionarios para mostrar en la tabla si lo deseas
        datos_consulta = df_resultado.to_dict(orient='records')

        return render_template(
            'mortalidad.html',
            resultados=datos_consulta,
            alcaldias_seleccionadas=alcaldias,
            periodo_inicio=p_inicio,
            periodo_fin=p_fin,
            parametro=parametro,
            datos_grafica=datos_grafica  # Pasamos los datos formateados a la plantilla
        )

    elif parametro == 'nivel_académico':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.clave_municipio,
                a.periodo,
                a.habitantes,
                a.p15ym_se AS preescolar,
                (a.p15pri_co + a.p15pri_in) AS primaria,
                (a.p15sec_co + a.p15sec_in) AS secundaria,
                a.p18ym_pb AS prepa_ymas,
                SUM(CASE WHEN p.nivel_academico IN (1, 2) THEN 1 ELSE 0 END) AS casos_preescolar,
                SUM(CASE WHEN p.nivel_academico IN (3, 4) THEN 1 ELSE 0 END) AS casos_primaria,
                SUM(CASE WHEN p.nivel_academico IN (5, 6) THEN 1 ELSE 0 END) AS casos_secundaria,
                SUM(CASE WHEN p.nivel_academico IN (7, 8, 9, 10) THEN 1 ELSE 0 END) AS casos_preparatoria_mas
            FROM Alcaldia a
            JOIN Paciente p 
                ON p.clave_municipio = a.id_alcaldia 
               AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND a.periodo BETWEEN :p_min AND :p_max
            GROUP BY 
                a.id_alcaldia,
                a.nombre,
                p.clave_municipio,
                a.periodo,
                a.habitantes,
                a.p15ym_se,
                a.p15pri_co,
                a.p15pri_in,
                a.p15sec_co,
                a.p15sec_in,
                a.p18ym_pb
            ORDER BY 
                a.periodo ASC, 
                a.nombre ASC;
        """)

        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                con=conn,
                params={
                    'alcaldias': tuple(alcaldias),
                    'p_min': periodo_min,
                    'p_max': periodo_max,
                },
            )

        if df.empty:
            return render_template(
                'nivel_academico.html',
                error='No se encontraron datos para la consulta.',
                alcaldias_seleccionadas=alcaldias,
                periodo_inicio=p_inicio,
                periodo_fin=p_fin,
                parametro=parametro,
            )

        # 1. Cálculo de las tasas de incidencia por cada 100k de cada grupo de nivel académico
        # Usamos fillna(0) para evitar divisiones entre cero
        df['tasa_preescolar'] = (
            (df['casos_preescolar'] / df['preescolar']).fillna(0) * 100000
        ).round(2)
        df['tasa_primaria'] = (
            (df['casos_primaria'] / df['primaria']).fillna(0) * 100000
        ).round(2)
        df['tasa_secundaria'] = (
            (df['casos_secundaria'] / df['secundaria']).fillna(0) * 100000
        ).round(2)
        df['tasa_prepa_ymas'] = (
            (df['casos_preparatoria_mas'] / df['prepa_ymas']).fillna(0) * 100000
        ).round(2)

        # 2. Periodos únicos para el eje X
        periodos_eje_x = sorted(df['periodo'].unique().tolist())

        # Paleta de colores para identificar las alcaldías
        colores = [
            '#007bff',
            '#28a745',
            '#dc3545',
            '#ffc107',
            '#17a2b8',
            '#6610f2',
            '#fd7e14',
        ]

        # Definición de los 4 grupos académicos para generar las 4 gráficas
        grupos_academicos = [
            {
                'key': 'tasa_preescolar',
                'titulo': 'Tasa de Casos - Preescolar / Sin Escolaridad',
            },
            {'key': 'tasa_primaria', 'titulo': 'Tasa de Casos - Primaria'},
            {'key': 'tasa_secundaria', 'titulo': 'Tasa de Casos - Secundaria'},
            {
                'key': 'tasa_prepa_ymas',
                'titulo': 'Tasa de Casos - Preparatoria o Superior',
            },
        ]

        graficas_data = []

        for grupo in grupos_academicos:
            datasets = []
            for i, alcaldia in enumerate(df['alcaldia'].unique()):
                df_alc = df[df['alcaldia'] == alcaldia]

                # Mapeo de tasas correspondientes al periodo
                tasas_map = dict(zip(df_alc['periodo'], df_alc[grupo['key']]))
                datos_serie = [
                    tasas_map.get(p, 0) for p in periodos_eje_x
                ]

                color = colores[i % len(colores)]
                datasets.append({
                    'label': alcaldia,
                    'data': datos_serie,
                    'borderColor': color,
                    'backgroundColor': color,
                    'borderWidth': 2,
                    'fill': False,
                    'tension': 0.2,
                })

            graficas_data.append({
                'titulo': grupo['titulo'],
                'periodos': periodos_eje_x,
                'datasets': datasets,
            })

        datos_consulta = df.to_dict(orient='records')

        return render_template(
            'nivel_academico.html',
            resultados=datos_consulta,
            alcaldias_seleccionadas=alcaldias,
            periodo_inicio=p_inicio,
            periodo_fin=p_fin,
            parametro=parametro,
            graficas=graficas_data,  # Contiene la información para las 4 gráficas
        )

    elif parametro == 'pobreza':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                a.periodo,
                a.pobreza_porcentaje,
                a.pobreza_poblacion,
                COUNT(p.sexo) AS casos_totales,
                a.habitantes
            FROM Alcaldia a
            JOIN Paciente p 
                ON p.clave_municipio = a.id_alcaldia 
               AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND a.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, a.periodo, a.pobreza_porcentaje, a.pobreza_poblacion, a.habitantes
            ORDER BY a.periodo ASC, a.nombre ASC;
        """)

        # Ejecutamos la consulta usando engine.connect() como en el bloque de mortalidad
        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                con=conn,
                params={
                    'alcaldias': tuple(alcaldias),
                    'p_min': periodo_min,
                    'p_max': periodo_max,
                },
            )

        if df.empty:
            return render_template(
                'pobreza.html',
                error='No se encontraron datos para la consulta.',
                alcaldias_seleccionadas=alcaldias,
                periodo_inicio=p_inicio,
                periodo_fin=p_fin,
                parametro=parametro,
            )

        # 1. Calculamos la tasa de mortalidad por cada 100k habitantes
        df['tasa_100k'] = (df['casos_totales'] / df['habitantes']) * 100000

        # 2. Factor de escala para el tamaño visual de la burbuja en px
        FACTOR_ESCALA = 0.15
        df['radio_burbuja'] = df['tasa_100k'] * FACTOR_ESCALA

        colores = [
            'rgba(255, 99, 132, 0.6)',
            'rgba(54, 162, 235, 0.6)',
            'rgba(255, 206, 86, 0.6)',
            'rgba(75, 192, 192, 0.6)',
            'rgba(153, 102, 255, 0.6)',
            'rgba(255, 159, 64, 0.6)',
        ]

        datasets = []
        for i, (alcaldia_nombre, group) in enumerate(df.groupby('alcaldia')):
            puntos = []
            for _, row in group.iterrows():
                puntos.append({
                    'x': int(row['periodo']),
                    'y': float(row['pobreza_porcentaje']),
                    'r': round(float(row['radio_burbuja']), 2),
                    'tasa_real': round(float(row['tasa_100k']), 2),
                    'casos': int(row['casos_totales']),
                })

            color = colores[i % len(colores)]
            datasets.append({
                'label': alcaldia_nombre,
                'data': puntos,
                'backgroundColor': color,
                'borderColor': color.replace('0.6', '1.0'),
                'borderWidth': 1,
            })

        datos_consulta = df.to_dict(orient='records')

        return render_template(
            'pobreza.html',
            resultados=datos_consulta,
            alcaldias_seleccionadas=alcaldias,
            periodo_inicio=p_inicio,
            periodo_fin=p_fin,
            parametro=parametro,
            datos_grafica=datasets,
        )

    elif parametro == 'edad':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                -- Agrupación de casos de pacientes por rango de edad
                COUNT(CASE WHEN p.edad BETWEEN 0 AND 14 THEN 1 END) AS casos_0a14,
                COUNT(CASE WHEN p.edad BETWEEN 15 AND 24 THEN 1 END) AS casos_15a24,
                COUNT(CASE WHEN p.edad BETWEEN 25 AND 59 THEN 1 END) AS casos_25a59,
                COUNT(CASE WHEN p.edad >= 60 THEN 1 END) AS casos_60ymas,
                -- Población por rango de edad por alcaldía y periodo
                MAX(a.p_0a14) AS pob_0a14,
                MAX(a.p_15a24) AS pob_15a24,
                MAX(a.p_25a59) AS pob_25a59, -- Asegúrate que la columna en la BD coincida con el nombre exacto
                MAX(a.p_60ymas) AS pob_60ymas
            FROM Paciente p
            JOIN Alcaldia a 
                ON p.clave_municipio = a.id_alcaldia 
               AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo
            ORDER BY p.periodo ASC, a.nombre ASC;
        """)

        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                con=conn,
                params={
                    'alcaldias': tuple(alcaldias),
                    'p_min': periodo_min,
                    'p_max': periodo_max,
                },
            )

        if df.empty:
            return render_template(
                'edad.html',
                error='No se encontraron datos para la consulta.',
                alcaldias_seleccionadas=alcaldias,
                periodo_inicio=p_inicio,
                periodo_fin=p_fin,
                parametro=parametro,
            )

        # 1. Cálculo de las tasas de incidencia por cada 100k de cada grupo de edad
        # Evitamos división entre cero con fillna(0) o condicionales
        df['tasa_0a14'] = (
            (df['casos_0a14'] / df['pob_0a14']).fillna(0) * 100000
        ).round(2)
        df['tasa_15a24'] = (
            (df['casos_15a24'] / df['pob_15a24']).fillna(0) * 100000
        ).round(2)
        df['tasa_25a59'] = (
            (df['casos_25a59'] / df['pob_25a59']).fillna(0) * 100000
        ).round(2)
        df['tasa_60ymas'] = (
            (df['casos_60ymas'] / df['pob_60ymas']).fillna(0) * 100000
        ).round(2)

        # 2. Obtenemos los periodos únicos para el eje X
        periodos_eje_x = sorted(df['periodo'].unique().tolist())

        # Palette de colores asignada por alcaldía
        colores = [
            '#007bff',
            '#28a745',
            '#dc3545',
            '#ffc107',
            '#17a2b8',
            '#6610f2',
            '#fd7e14',
        ]

        # Definiendo los 4 grupos de edad para estructurar las 4 gráficas
        grupos_edad = [
            {'key': 'tasa_0a14', 'titulo': 'Tasa de Mortalidad (0 a 14 años)'},
            {
                'key': 'tasa_15a24',
                'titulo': 'Tasa de Mortalidad (15 a 24 años)',
            },
            {
                'key': 'tasa_25a59',
                'titulo': 'Tasa de Mortalidad (25 a 59 años)',
            },
            {
                'key': 'tasa_60ymas',
                'titulo': 'Tasa de Mortalidad (60 o más años)',
            },
        ]

        graficas_data = []

        for grupo in grupos_edad:
            datasets = []
            for i, alcaldia in enumerate(df['alcaldia'].unique()):
                df_alc = df[df['alcaldia'] == alcaldia]

                # Mapear las tasas correspondientes al periodo
                tasas_map = dict(zip(df_alc['periodo'], df_alc[grupo['key']]))
                datos_serie = [
                    tasas_map.get(p, 0) for p in periodos_eje_x
                ]

                color = colores[i % len(colores)]
                datasets.append({
                    'label': alcaldia,
                    'data': datos_serie,
                    'borderColor': color,
                    'backgroundColor': color,
                    'borderWidth': 2,
                    'fill': False,
                    'tension': 0.2,
                })

            graficas_data.append({
                'titulo': grupo['titulo'],
                'periodos': periodos_eje_x,
                'datasets': datasets,
            })

        datos_consulta = df.to_dict(orient='records')

        return render_template(
            'edad.html',
            resultados=datos_consulta,
            alcaldias_seleccionadas=alcaldias,
            periodo_inicio=p_inicio,
            periodo_fin=p_fin,
            parametro=parametro,
            graficas=graficas_data,  # Contiene la información para las 4 gráficas
        )

    elif parametro == 'sexo':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                -- Agregación condicional por sexo (1 y 2)
                COUNT(CASE WHEN p.sexo = 1 THEN 1 END) AS casos_hombres,
                COUNT(CASE WHEN p.sexo = 2 THEN 1 END) AS casos_mujeres,
                MAX(a.pobmas) AS pob_masculina,
                MAX(a.pobfem) AS pob_femenina
            FROM Paciente p
            JOIN Alcaldia a 
                ON p.clave_municipio = a.id_alcaldia 
               AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo
            ORDER BY p.periodo ASC, a.nombre ASC;
        """)

        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                con=conn,
                params={
                    'alcaldias': tuple(alcaldias),
                    'p_min': periodo_min,
                    'p_max': periodo_max,
                },
            )

        if df.empty:
            return render_template(
                'sexo.html',
                error='No se encontraron datos para la consulta.',
                alcaldias_seleccionadas=alcaldias,
                periodo_inicio=p_inicio,
                periodo_fin=p_fin,
                parametro=parametro,
            )

        # 1. Cálculo de las tasas de casos por cada 100k habitantes (población masculina y femenina)
        df['tasa_hombres'] = (
            (df['casos_hombres'] / df['pob_masculina']).fillna(0) * 100000
        ).round(2)
        df['tasa_mujeres'] = (
            (df['casos_mujeres'] / df['pob_femenina']).fillna(0) * 100000
        ).round(2)

        # 2. Eje X con los periodos únicos ordenados
        periodos_eje_x = sorted(df['periodo'].unique().tolist())

        # Paleta de colores para identificar cada alcaldía
        colores = [
            '#007bff',
            '#28a745',
            '#dc3545',
            '#ffc107',
            '#17a2b8',
            '#6610f2',
            '#fd7e14',
        ]

        # Definición de los 2 grupos para estructurar las 2 gráficas
        grupos_sexo = [
            {'key': 'tasa_hombres', 'titulo': 'Tasa de Casos en Hombres (por 100k Hombres)'},
            {'key': 'tasa_mujeres', 'titulo': 'Tasa de Casos en Mujeres (por 100k Mujeres)'},
        ]

        graficas_data = []

        for grupo in grupos_sexo:
            datasets = []
            for i, alcaldia in enumerate(df['alcaldia'].unique()):
                df_alc = df[df['alcaldia'] == alcaldia]

                # Mapeo de tasas asegurando que coincidan con cada periodo en el eje X
                tasas_map = dict(zip(df_alc['periodo'], df_alc[grupo['key']]))
                datos_serie = [
                    tasas_map.get(p, 0) for p in periodos_eje_x
                ]

                color = colores[i % len(colores)]
                datasets.append({
                    'label': alcaldia,
                    'data': datos_serie,
                    'borderColor': color,
                    'backgroundColor': color,
                    'borderWidth': 2,
                    'fill': False,
                    'tension': 0.2,
                })

            graficas_data.append({
                'titulo': grupo['titulo'],
                'periodos': periodos_eje_x,
                'datasets': datasets,
            })

        datos_consulta = df.to_dict(orient='records')

        return render_template(
            'sexo.html',
            resultados=datos_consulta,
            alcaldias_seleccionadas=alcaldias,
            periodo_inicio=p_inicio,
            periodo_fin=p_fin,
            parametro=parametro,
            graficas=graficas_data,  # Datos estructurados para las 2 gráficas
        )

    elif parametro == 'dmt':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                -- Agregación condicional por tipo de diabetes (1 y 2)
                COUNT(CASE WHEN p.dmt = 1 THEN 1 END) AS casos_dmt1,
                COUNT(CASE WHEN p.dmt = 2 THEN 1 END) AS casos_dmt2,
                MAX(a.habitantes) AS habitantes
            FROM Paciente p
            JOIN Alcaldia a 
                ON p.clave_municipio = a.id_alcaldia 
               AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo
            ORDER BY p.periodo ASC, a.nombre ASC;
        """)

        with engine.connect() as conn:
            df = pd.read_sql(
                query,
                con=conn,
                params={
                    'alcaldias': tuple(alcaldias),
                    'p_min': periodo_min,
                    'p_max': periodo_max,
                },
            )

        if df.empty:
            return render_template(
                'dmt.html',
                error='No se encontraron datos para la consulta.',
                alcaldias_seleccionadas=alcaldias,
                periodo_inicio=p_inicio,
                periodo_fin=p_fin,
                parametro=parametro,
            )

        # 1. Cálculo de las tasas de casos por cada 100k habitantes
        df['tasa_dmt1'] = (
            (df['casos_dmt1'] / df['habitantes']).fillna(0) * 100000
        ).round(2)
        df['tasa_dmt2'] = (
            (df['casos_dmt2'] / df['habitantes']).fillna(0) * 100000
        ).round(2)

        # 2. Eje X con los periodos únicos ordenados
        periodos_eje_x = sorted(df['periodo'].unique().tolist())

        # Paleta de colores para identificar cada alcaldía
        colores = [
            '#007bff',
            '#28a745',
            '#dc3545',
            '#ffc107',
            '#17a2b8',
            '#6610f2',
            '#fd7e14',
        ]

        # Definición de los 2 tipos de DMT para estructurar las 2 gráficas
        tipos_dmt = [
            {'key': 'tasa_dmt1', 'titulo': 'Tasa de Diabetes Tipo 1'},
            {'key': 'tasa_dmt2', 'titulo': 'Tasa de Diabetes Tipo 2'},
        ]

        graficas_data = []

        for tipo in tipos_dmt:
            datasets = []
            for i, alcaldia in enumerate(df['alcaldia'].unique()):
                df_alc = df[df['alcaldia'] == alcaldia]

                # Mapeo de tasas asegurando que coincidan con cada periodo en el eje X
                tasas_map = dict(zip(df_alc['periodo'], df_alc[tipo['key']]))
                datos_serie = [
                    tasas_map.get(p, 0) for p in periodos_eje_x
                ]

                color = colores[i % len(colores)]
                datasets.append({
                    'label': alcaldia,
                    'data': datos_serie,
                    'borderColor': color,
                    'backgroundColor': color,
                    'borderWidth': 2,
                    'fill': False,
                    'tension': 0.2,
                })

            graficas_data.append({
                'titulo': tipo['titulo'],
                'periodos': periodos_eje_x,
                'datasets': datasets,
            })

        datos_consulta = df.to_dict(orient='records')

        return render_template(
            'dmt.html',
            resultados=datos_consulta,
            alcaldias_seleccionadas=alcaldias,
            periodo_inicio=p_inicio,
            periodo_fin=p_fin,
            parametro=parametro,
            graficas=graficas_data,  # Pasa las 2 estructuras de gráfica a la plantilla
        )

    # # 3. Ejecutar la consulta en la base de datos
    # with engine.connect() as conn:
    #     df_resultado = pd.read_sql(
    #         query,
    #         con=conn,
    #         params={
    #             'alcaldias': tuple(alcaldias),
    #             'p_min': periodo_min,
    #             'p_max': periodo_max,
    #         },
    #     )

    # # 4. Convertir DataFrame a lista de diccionarios para Jinja2
    # datos_consulta = df_resultado.to_dict(orient='records')

    # # 5. Retornar vista pasando los resultados
    # return render_template(
    #     'consultas.html',
    #     resultados=datos_consulta,
    #     alcaldias_seleccionadas=alcaldias,
    #     periodo_inicio=p_inicio,
    #     periodo_fin=p_fin,
    #     parametro=parametro,
        
    # )


# Arrancar el servidor de desarrollo en local
if __name__ == "__main__":
    app.run(debug=True)