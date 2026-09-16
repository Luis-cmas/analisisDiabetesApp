from flask import Flask,render_template #importamos el objeto Flask (el constructor de la aplicacion) de la libreria flask
#render template es para poder llamar a los html y ponerlos en la app

app = Flask(__name__)#creamos el objeto(la aplicacion), poniendo el parametro __name__
# este parametro es una variable especial de python que devuelve el nombre del script, al ejecutar el programa 
# pone por default __name__ = "__main__"
# en caso de ser un script importado desde otro script pone __name__ = "nombre del script/programa", en este caso = "script1"

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

if __name__ == "__main__":
    app.run(debug = True)