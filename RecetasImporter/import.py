import sys
import getopt
import json
import peewee as pw
import requests
from bs4 import BeautifulSoup


URL = 'https://test-es.edamam.com/search'
APP_ID = '751bb7bc'
APP_KEY = '706763ea01b39a5a2ea5c8ef9becd93b'

NUTRIENTES_ID = [
    'CA',
    'CHOCDF',
    'CHOLE',
    'FAMS',
    'FAPU',
    'SUGAR',
    'FAT',
    'FATRN',
    'FE',
    'FIBTG',
    'FOLDFE',
    'K',
    'MG',
    'NA',
    'VITB6A'
]

db = pw.SqliteDatabase('recipes.db')


class Receta(pw.Model):
    nombre = pw.CharField()
    imagen = pw.CharField()
    url = pw.CharField()
    atribucion = pw.CharField()
    duracion = pw.CharField()
    valoracion = pw.FloatField(default=0)
    calorias = pw.FloatField()
    peso = pw.FloatField()
    raciones = pw.FloatField()
    dificultad = pw.CharField()
    cocina = pw.CharField()
    pasos = pw.TextField(null=True)

    class Meta:
        database = db


class Ingrediente(pw.Model):
    nombre = pw.CharField()

    class Meta:
        database = db


class RecetaIngrediente(pw.Model):
    receta = pw.ForeignKeyField(Receta)
    ingrediente = pw.ForeignKeyField(Ingrediente)
    peso = pw.IntegerField()

    class Meta:
        database = db


class Tag(pw.Model):
    nombre = pw.CharField()

    class Meta:
        database = db


class RecetaTag(pw.Model):
    receta = pw.ForeignKeyField(Receta)
    tag = pw.ForeignKeyField(Tag)

    class Meta:
        database = db


class Nutriente(pw.Model):
    nombre = pw.CharField()

    class Meta:
        database = db


class RecetaNutriente(pw.Model):
    receta = pw.ForeignKeyField(Receta)
    nutriente = pw.ForeignKeyField(Nutriente)
    cantidad = pw.FloatField()
    unidad = pw.CharField()
    porcentaje_diario = pw.FloatField()

    class Meta:
        database = db


"""
Parser para Comida Kraft
"""


def get_pasos_kraft(url):
    # Proxy TOR necesario. Web con Geo Block (USA, Canada, etc.)
    session = requests.session()
    session.proxies = {}
    session.proxies['http'] = 'socks5h://localhost:9050'
    session.proxies['https'] = 'socks5h://localhost:9050'

    r = session.get(url)

    soup = BeautifulSoup(r.text, 'html.parser')
    pasos = soup.find_all("div", "krRecipeMakeItText")

    pasos_json = dict()
    paso_idx = 1

    for paso in pasos:
        paso = paso.text
        pasos_json[str(paso_idx)] = paso
        paso_idx += 1

    return json.dumps(pasos_json, ensure_ascii=False).encode('utf8')


"""
Parser Que Rica Vida
"""


def get_pasos_ricavida(url):
    r = requests.get(url)

    soup = BeautifulSoup(r.text, 'html.parser')
    pasos = soup.find_all("div", "recipePartStepDescription")

    pasos_json = dict()
    paso_idx = 1

    for paso in pasos:
        paso = paso.text.strip()
        pasos_json[str(paso_idx)] = paso
        paso_idx += 1

    return json.dumps(pasos_json, ensure_ascii=False).encode('utf8')


# Parsers de los pasos
SCRAPPING = [
    ('comidakraft.com', get_pasos_kraft),
    ('quericavida.com', get_pasos_ricavida)
]


def procesar(recetas, dificultad):
    duracion = recetas['params']['time']
    cocina = recetas['params']['q'][0]
    duracion = duracion[0] if len(
        duracion) == 1 else duracion[0] + '-' + duracion[1]
    recetas = recetas['hits']

    for r in recetas:
        receta = r['recipe']
        nombre = receta['label']
        url = receta['url']
        atribucion = receta['source']
        imagen = receta['image']
        calorias = receta['calories']
        peso = receta['totalWeight']
        raciones = receta['yield']

        nueva = False
        try:
            # ¿Existe ya esa receta?
            receta_obj = Receta.get(Receta.nombre == nombre)
        except pw.DoesNotExist as error:
            nueva = True

        if nueva:
            # Scraping de los pasos (solo si es una receta nueva, consume tiempo...)
            pasos_disponibles = [web[1] for web in SCRAPPING if web[0] in url]
            if len(pasos_disponibles) > 0:
                pasos = pasos_disponibles[0](url)
            else:
                pasos = ""

            receta_obj = Receta.create(nombre=nombre,
                                       imagen=imagen,
                                       url=url,
                                       atribucion=atribucion,
                                       duracion=duracion,
                                       valoracion=0,
                                       calorias=calorias,
                                       peso=peso,
                                       raciones=raciones,
                                       dificultad=dificultad,
                                       cocina=cocina,
                                       pasos=pasos)

            tags = receta['dietLabels'] + receta['healthLabels']

            for t in tags:

                tag, creado = Tag.get_or_create(nombre=t)
                ingre_tag = RecetaTag.create(receta=receta_obj.id, tag=tag.id)

            ingredientes = receta['ingredients']

            for i in ingredientes:
                nombre = i['text']
                peso = float(i['weight'])

                ingrediente, creado = Ingrediente.get_or_create(nombre=nombre)
                receta_ingre = RecetaIngrediente.create(receta=receta_obj.id,
                                                        ingrediente=ingrediente.id,
                                                        peso=peso)

            nutrientes = receta['totalNutrients']
            diario = receta['totalDaily']

            for n in range(len(NUTRIENTES_ID)):
                if NUTRIENTES_ID[n] in nutrientes and NUTRIENTES_ID[n] in diario:
                    nutriente = nutrientes[NUTRIENTES_ID[n]]
                    nutriente_diario = diario[NUTRIENTES_ID[n]]
                    nombre = nutriente['label']
                    cantidad = nutriente['quantity']
                    unidad = nutriente['unit']
                    porcentaje_diario = nutriente_diario['quantity']
                    nutriente, creado = Nutriente.get_or_create(nombre=nombre)
                    receta_nutri = RecetaNutriente.create(receta=receta_obj.id,
                                                          nutriente=nutriente.id,
                                                          cantidad=cantidad,
                                                          unidad=unidad,
                                                          porcentaje_diario=porcentaje_diario)


def get_recipes(query, limite, tiempo, dificultad):
    payload = {'app_id': APP_ID,
               'app_key': APP_KEY,
               'q': query,
               'time': tiempo,
               'from': limite[0],
               'to': limite[1]}

    r = requests.get(URL, params=payload)

    procesar(r.json(), dificultad)


def main(argv):
    query = None
    tiempo = None
    limite_min = -1
    limite_max = -1
    dificultad = None

    try:
        opts, args = getopt.getopt(
            argv, "hs:e:q:t:", ["start=", "end=", "query=", "time="])
    except getopt.GetoptError:
        print('import.py -s <start> -e <end> -q <busqueda> -t <tiempo>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('import.py -s <start> -e <end> -q <busqueda> -t <tiempo>')
            sys.exit()
        elif opt in ("-s", "--from"):
            limite_min = arg
        elif opt in ("-e", "--to"):
            limite_max = arg
        elif opt in ("-q", "--query"):
            query = arg
        elif opt in ("-t", "--time"):
            tiempo = arg

    limite = (limite_min, limite_max)

    if not query or not tiempo or limite[0] == -1 or limite[1] == -1:
        print('import.py -s <start> -e <end> -q <busqueda> -t <tiempo>')
        sys.exit(2)
    else:
        tiempo = tiempo.split('-')
        max_tiempo = None

        if (len(tiempo) == 2):
            max_tiempo = int(tiempo[1])
        else:
            max_tiempo = int(tiempo[0])

        if max_tiempo < 40:
            dificultad = 'Fácil'
        elif max_tiempo < 70:
            dificultad = 'Medio'
        else:
            dificultad = 'Difícil'

    db.connect()
    db.create_tables([Receta, Ingrediente, Tag, RecetaIngrediente,
                      RecetaTag, Nutriente, RecetaNutriente])
    get_recipes(query, limite, tiempo, dificultad)
    db.close()


if __name__ == '__main__':
    main(sys.argv[1:])
