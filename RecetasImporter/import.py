import sys
import getopt
import json
import logging
from io import open as iopen
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


class Recipe(pw.Model):
    name = pw.CharField()
    url = pw.CharField()
    attribution = pw.CharField()
    duration = pw.IntegerField()
    calories = pw.FloatField()
    weight = pw.FloatField()
    rations = pw.FloatField()
    difficulty = pw.CharField()
    cuisine = pw.CharField()
    steps = pw.TextField(null=True)
    user_id = pw.IntegerField()

    class Meta:
        db_table = 'recipe'
        database = db


class Ingredient(pw.Model):
    name = pw.CharField()

    class Meta:
        db_table = 'ingredient'
        database = db


class RecipeIngredient(pw.Model):
    weight = pw.IntegerField()
    recipe_id = pw.ForeignKeyField(Recipe)
    ingredient_id = pw.ForeignKeyField(Ingredient)

    class Meta:
        db_table = 'recipe_ingredient'
        database = db


class Tag(pw.Model):
    tag = pw.CharField()

    class Meta:
        db_table = 'tag'
        database = db


class RecipeTags(pw.Model):
    recipe_id = pw.ForeignKeyField(Recipe)
    tags_id = pw.ForeignKeyField(Tag)

    class Meta:
        db_table = 'recipe_tags'
        primary_key = pw.CompositeKey('recipe_id', 'tags_id')
        database = db


class Nutrient(pw.Model):
    nutrient = pw.CharField()

    class Meta:
        db_table = 'nutrient'
        database = db


class RecipeNutrient(pw.Model):
    cuantity = pw.FloatField()
    daily_percentage = pw.FloatField()
    unit = pw.CharField()
    nutrient_id = pw.ForeignKeyField(Nutrient)
    recipe_id = pw.ForeignKeyField(Recipe)

    class Meta:
        db_table = 'recipe_nutrient'
        database = db


def file_extension(file_url):
    file_suffix = file_url.split('.')[-1]
    return file_suffix


def download_img(img, name):
    with iopen('img/' + name, 'wb') as file:
        file.write(img)


"""
Parser para Comida Kraft
"""


def get_pasos_kraft(id_db, url, imagen):
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

    r = session.get(imagen)
    if r.status_code == requests.codes.ok:
        download_img(r.content, str(id_db) + '.' + file_extension(imagen))

    return json.dumps(pasos_json, ensure_ascii=False).encode('utf8')


"""
Parser Que Rica Vida
"""


def get_pasos_ricavida(id_db, url, imagen):
    r = requests.get(url)

    soup = BeautifulSoup(r.text, 'html.parser')
    pasos = soup.find_all("div", "recipePartStepDescription")

    pasos_json = dict()
    paso_idx = 1

    for paso in pasos:
        paso = paso.text.strip()
        pasos_json[str(paso_idx)] = paso
        paso_idx += 1

    r = requests.get(imagen)
    if r.status_code == requests.codes.ok:
        download_img(r.content, str(id_db) + '.' + file_extension(imagen))

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

    idx = 1

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
            receta_obj = Recipe.get(Recipe.name == nombre)
        except pw.DoesNotExist as error:
            nueva = True

        if nueva:
            # Scraping de los pasos (solo si es una receta nueva, consume tiempo...)
            pasos_disponibles = [web[1] for web in SCRAPPING if web[0] in url]
            if len(pasos_disponibles) > 0:
                pasos = pasos_disponibles[0](idx, url, imagen)
            else:
                pasos = ""

            receta_obj = Recipe.create(attribution=atribucion,
                                       calories=calorias,
                                       cuisine=cocina,
                                       difficulty=dificultad,
                                       duration=duracion,
                                       name=nombre,
                                       rations=raciones,
                                       steps=pasos,
                                       url=url,
                                       weight=peso,
                                       user_id=1)

            tags = receta['dietLabels'] + receta['healthLabels']

            for t in tags:

                tag, creado = Tag.get_or_create(tag=t)
                ingre_tag = RecipeTags.create(
                    recipe_id=receta_obj.id, tags_id=tag.id)

            ingredientes = receta['ingredients']

            for i in ingredientes:
                nombre = i['text']
                peso = float(i['weight'])

                ingrediente, creado = Ingredient.get_or_create(name=nombre)
                receta_ingre = RecipeIngredient.create(weight=peso,
                                                       ingredient_id=ingrediente.id,
                                                       recipe_id=receta_obj.id)

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
                    nutriente, creado = Nutrient.get_or_create(nutrient=nombre)
                    receta_nutri = RecipeNutrient.create(cuantity=cantidad,
                                                         daily_percentage=porcentaje_diario,
                                                         unit=unidad,
                                                         nutrient_id=nutriente.id,
                                                         recipe_id=receta_obj.id)
        idx += 1


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
    db.create_tables([Recipe, Ingredient, Tag, RecipeIngredient,
                      RecipeTags, Nutrient, RecipeNutrient])
    logger = logging.getLogger('peewee')
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)
    get_recipes(query, limite, tiempo, dificultad)
    db.close()


if __name__ == '__main__':
    main(sys.argv[1:])
