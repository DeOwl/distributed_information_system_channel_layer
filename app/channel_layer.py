import falcon
import logging
import falcon.asgi
import json
from bitarray import bitarray
from random import randint, random
import requests

import os
FORWARD_TEXT_URL = os.environ['FORWARD_TEXT_URL']
REQUEST_SEGMENT_SIZE = int(os.environ['REQUEST_SEGMENT_SIZE'])
ERROR_CHANCE = float(os.environ['ERROR_CHANCE'])
LOSS_CHANCE = float(os.environ['LOSS_CHANCE'])

logging.basicConfig(level=logging.INFO)

def decode_hammington(bit_array : bitarray):
    decoded = bitarray()
    for i in range(len(bit_array) // 7):
        encoded_7 = bit_array[i * 7: ((i + 1) * 7)]

        syndrome = str(encoded_7[6] ^ encoded_7[5] ^ encoded_7[4] ^ encoded_7[2]) + \
                    str(encoded_7[5] ^ encoded_7[4] ^ encoded_7[3] ^ encoded_7[1]) + \
                    str(encoded_7[6] ^ encoded_7[5] ^ encoded_7[3] ^ encoded_7[0])
        match syndrome:
            case "001":
                mask = "0000001"
            case "010":
                mask = "0000010"
            case "011":
                mask = "0001000"
            case "100":
                mask = "0000100"
            case "101":
                mask = "1000000"
            case "110":
                mask = "0010000"
            case "111": 
                mask = "0100000"
            case "000":
                mask = "0000000"
        mask = bitarray(mask)
        mask.reverse()
        encoded_7 = encoded_7 ^ mask
        decoded.extend(encoded_7[3:])
    return decoded
def encode_hemmington(doc : str):
    encoded = doc.encode()
    four_bit_list = []
    for byte in encoded:
        four_bit_list.append(byte >> 4)
        four_bit_list.append(byte & 15)

    bitarr = bitarray()
    for i in four_bit_list:
        bitarr.append((i & 1) ^ ((i >> 1) & 1) ^ ((i >> 3) & 1))
        bitarr.append(((i >> 1) & 1) ^ ((i >> 2) & 1) ^ ((i >> 3) & 1))
        bitarr.append((i & 1) ^ ((i >> 1) & 1) ^ ((i >> 2) & 1))
        bitarr.extend(f'{i:04b}')

    return bitarr

def add_error(bit_array: bitarray):
    if (random() <= ERROR_CHANCE):
        error_pos = randint(1, len(bit_array))
        error = bitarray('0') * error_pos
        error[-1] = True
        error.extend('0' * (len(bit_array) - error_pos))
        return bit_array ^ error
    return bit_array

def should_lose():
    return random() <= LOSS_CHANCE

class ThingsResource:
    async def on_post(self, req, resp):
        doc = req.context.doc
        bitarr = encode_hemmington(doc)
        with_error = add_error(bitarr)
        decoded = decode_hammington(with_error)
        if (should_lose()):
            #Потерять кадр
            resp.status = falcon.HTTP_500
            raise falcon.HTTPInternalServerError(
                    title='Кадр был утерян'
                )
        else:
            #Отправить на endpoint ответ и вернуть "200"
            try:
                response = requests.post(FORWARD_TEXT_URL, data=decoded.tobytes(), headers={'Content-Type': 'application/json; charset=UTF-8'})
            except requests.ConnectionError as e:
                raise falcon.HTTPServiceUnavailable(title="Ошибка подключения к сетевому уровню.")
            if (response.status_code == 200):
                resp.status = falcon.HTTP_200
                resp.content_type = falcon.HTTP_NO_CONTENT
            else:
                raise falcon.HTTPStatus(status=response.status_code, text=response.content.decode())


class RequireJSON:
    async def process_request(self, req, resp):
        if req.method == 'POST':
            if not req.content_type:
                raise falcon.HTTPUnsupportedMediaType(
                    title='API поддерживает только запросы с телом.'
                )
            if 'application/json' not in req.content_type:
                raise falcon.HTTPUnsupportedMediaType(
                    title='API поддерживает только запросы JSON.'
                )


class JSONTranslator:
    async def process_request(self, req, resp):
        # NOTE: Test explicitly for 0, since this property could be None in
        # the case that the Content-Length header is missing (in which case we
        # can't know if there is a body without actually attempting to read
        # it from the request stream.)
        if req.content_length > REQUEST_SEGMENT_SIZE:
            raise falcon.HTTPBadRequest(
                title='НЕПРАВИЛЬНЫЙ РАЗМЕР ТЕЛА',
                description=f'Ожидается запрос с телом не более {REQUEST_SEGMENT_SIZE} байт. Получен: {req.content_length} байт',
            )
        body = await req.stream.read()
        if not body:
            raise falcon.HTTPBadRequest(
                title='ПУСТОЕ ТЕЛО ЗАПРОСА',
                description='ОЖИДАЕТСЯ ПРАВИЛЬНЫЙ JSON документ',
            )

        try:
            req.context.doc = body.decode('utf-8')
            data = json.loads(req.context.doc)

        except (ValueError, UnicodeDecodeError):
            description = (
                'Не смог расшифровать тело. Либо отправлен неправильный JSON либо он не закодирован по UTF-8'
            )

            raise falcon.HTTPBadRequest(title='кривой JSON', description=description)


app = falcon.asgi.App(
    middleware=[
        RequireJSON(),
        JSONTranslator()
    ]
)

things = ThingsResource()
app.add_route("/code", things)