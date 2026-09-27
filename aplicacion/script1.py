from flask import Flask, render_template, request
from sqlalchemy import create_engine, text
import pandas as pd
from dotenv import load_dotenv
import os
#importamos el objeto Flask (el constructor de la aplicacion) de la libreria flask
#render template es para poder llamar a los html y ponerlos en la app

app = Flask(__name__)#creamos el objeto(la aplicacion), poniendo el parametro __name__
# este parametro es una variable especial de python que devuelve el nombre del script, al ejecutar el programa 
# pone por default __name__ = "__main__"
# en caso de ser un script importado desde otro script pone __name__ = "nombre del script/programa", en este caso = "script1"
load_dotenv()
#db_password = os.getenv("PASSWORD")
usuario_bd = os.getenv("USUARIO")
pass_bd = os.getenv("PASSWORD")
host_bd = os.getenv("HOST")
nombre_bd = os.getenv("NOMBRE_BD")
cadena_conexion = f"mysql+pymysql://{usuario_bd}:{pass_bd}@{host_bd}/{nombre_bd}"
#engine = create_engine(cadena_conexion)


@app.route('/')
def index():# la funcion home, se asocia a la ruta "/", por lo que aqui podemos empezar a instertar distinas url con distintas paginas
    return render_template("index.html")
#Ojo : recuerda que no pueden existir funciones con el mismo nombre, aun si estan en distinto url

# @app.route('/consultas/')
# def consultas():
#     return render_template("consultas.html")

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
        return "Por favor seleccione un periodo mas largo.", 400

    if not alcaldias:
        return "Por favor selecciona al menos una alcaldía.", 400

    # 2. Construcción dinámica de la consulta SQL según el parámetro seleccionado
    if parametro == 'mortalidad':
        # Conteo total de casos/pacientes por alcaldía y periodo
        query = text("""
            SELECT 
                a.nombre AS alcaldia, 
                p.periodo, 
                COUNT(p.dmt) AS total_casos
            FROM Paciente p
            JOIN Alcaldia a ON p.clave_municipio = a.id_alcaldia AND p.periodo = a.periodo
            WHERE a.nombre IN :alcaldias 
              AND p.periodo BETWEEN :p_min AND :p_max
            GROUP BY a.nombre, p.periodo
            ORDER BY p.periodo ASC, a.nombre ASC;
        """)

    elif parametro == 'nivel_académico':
        # Promedio de escolaridad e indicadores educativos de la tabla Alcaldia
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
        # Porcentajes y total de población en pobreza
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
        # Agrupación por edad o rangos en Paciente
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
        # Distribución de casos por sexo (1=Hombre, 2=Mujer)
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
        # Casos desglosados por tipo de diabetes (dmt)
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

    # 3. Ejecutar la consulta en la base de datos
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

    # 4. Convertir DataFrame a lista de diccionarios para Jinja2
    datos_consulta = df_resultado.to_dict(orient='records')

    # 5. Retornar vista pasando los resultados
    return render_template(
        'consultas.html',
        resultados=datos_consulta,
        alcaldias_seleccionadas=alcaldias,
        periodo_inicio=p_inicio,
        periodo_fin=p_fin,
        parametro=parametro,
    )

if __name__ == "__main__":
    app.run(debug = True)