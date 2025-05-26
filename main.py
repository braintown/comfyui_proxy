import websocket #NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
import uuid
import json
import urllib.request
import urllib.parse
import os

prompt_text = json.dumps("sam2.json")
server_address = "localhost:8888"
client_id = str(uuid.uuid4())

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())
def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()

def get_images(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_images = {}
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break #Execution is done
        else:
            # If you want to be able to decode the binary stream for latent previews, here is how you can do it:
            # bytesIO = BytesIO(out[8:])
            # preview_image = Image.open(bytesIO) # This is your preview in PIL image format, store it in a global
            continue #previews are binary data

    history = get_history(prompt_id)[prompt_id]
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        images_output = []
        if 'images' in node_output:
            for image in node_output['images']:
                image_data = get_image(image['filename'], image['subfolder'], image['type'])
                images_output.append(image_data)
        output_images[node_id] = images_output

    return output_images



prompt = json.loads(prompt_text)
#set the text prompt for our positive CLIPTextEncode
# prompt["19"]["inputs"]["Text"] = "car"

# prompt["25"]["inputs"]["url"] = "https://oss.gempoll.com/img/211c677a23064c71aac8fdb5a17cf194.mp4"

# # car： https://oss.gempoll.com/img/2a52c2e11a594fcea3dc54548560b0c4.mp4
# # girl： https://oss.gempoll.com/img/645bfe14eec64a6ea6c8ca0ff9b65c9a.mp4
# # car_short:https://oss.gempoll.com/img/211c677a23064c71aac8fdb5a17cf194.mp4


# #set the seed for our KSampler node
prompt["74"]["fixed_seed"]= "1221"

ws = websocket.WebSocket()
ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
images = get_images(ws, prompt)
# 修改最后几行代码
# 在文件开头添加输出目录路径
output_dir = "test"
os.makedirs(output_dir, exist_ok=True)

# 修改保存图片的代码
for node_id, image_list in images.items():
    for i, image_data in enumerate(image_list):
        output_path = os.path.join(output_dir, f"{i:04d}.png")
        with open(output_path, "wb") as f:
            f.write(image_data)

ws.close()
