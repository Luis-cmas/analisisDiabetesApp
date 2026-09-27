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
    engine = create_engine(cadena_conexion)
    print(f"-> Túnel SSH iniciado en el puerto local: {tunnel.local_bind_port}")
else:
    # ------------------------------------------------------------------
    # ENTORNO PRODUCCIÓN: Conexión directa
    # ------------------------------------------------------------------
    cadena_conexion = f"mysql+pymysql://{usuario_bd}:{pass_bd}@{host_bd}/{nombre_bd}"
    engine = create_engine(cadena_conexion)


# --- RUTAS DE FLASK ---

@app.route('/')
def index():
    return render_template("index.html")


@app.route('/consulta/')
def consulta():
    return render_template("consultas.html")


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
                nombre AS alcaldia,
                periodo,
                habitantes,
                p15ym_se AS sin_escolaridad,
                p15pri_co AS primaria_completa,
                p15sec_co AS secundaria_completa
            FROM Alcaldia
            WHERE nombre IN :alcaldias
              AND periodo BETWEEN :p_min AND :p_max
            ORDER BY periodo ASC, nombre ASC;
        """)

    elif parametro == 'pobreza':
        query = text("""
            SELECT
                nombre AS alcaldia,
                periodo,
                pobreza_porcentaje,
                pobreza_extrema_porcentaje,
                pobreza_moderada_porcentaje,
                pobreza_poblacion
            FROM Alcaldia
            WHERE nombre IN :alcaldias
              AND periodo BETWEEN :p_min AND :p_max
            ORDER BY periodo ASC, nombre ASC;
        """)

    elif parametro == 'edad':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                p.edad,
                COUNT(*) AS total_pacientes
            FROM Paciente p
            JOIN Alcaldia a ON p.clave_municipio = a.id_alcaldia AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo, p.edad
            ORDER BY p.periodo ASC, p.edad ASC;
        """)

    elif parametro == 'sexo':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                p.sexo,
                COUNT(*) AS total_pacientes
            FROM Paciente p
            JOIN Alcaldia a ON p.clave_municipio = a.id_alcaldia AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo, p.sexo
            ORDER BY p.periodo ASC, p.sexo ASC;
        """)

    elif parametro == 'dmt':
        query = text("""
            SELECT
                a.nombre AS alcaldia,
                p.periodo,
                p.dmt AS tipo_diabetes,
                COUNT(*) AS total_pacientes
            FROM Paciente p
            JOIN Alcaldia a ON p.clave_municipio = a.id_alcaldia AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo, p.dmt
            ORDER BY p.periodo ASC, p.dmt ASC;
        """)

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