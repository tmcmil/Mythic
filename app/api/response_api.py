from app import apfell, db_objects
from sanic.response import json
from app.database_models.model import Task, Response
import base64
from sanic_jwt.decorators import protected, inject_user
from app.api.file_api import create_filemeta_in_database_func, download_file_to_disk_func
import json as js


# This gets all responses in the database
@apfell.route(apfell.config['API_BASE'] + "/responses/", methods=['GET'])
@inject_user()
@protected()
async def get_all_responses(request, user):
    try:
        all_responses = await db_objects.execute(Response.select())
    except Exception as e:
        return json({'status': 'error',
                     'error': 'Cannot get responses'})
    return json([c.to_json() for c in all_responses])


# Get a single response
@apfell.route(apfell.config['API_BASE'] + "/response/<rid:int>", methods=['GET'])
@inject_user()
@protected()
async def get_one_response(request, user, rid):
    try:
        resp = await db_objects.get(Response, id=rid)
    except Exception as e:
        return json({'status': 'error', 'error': 'Cannot get that response'})
    return json(resp.to_json())


# implant calling back to update with base64 encoded response from executing a task
# We don't add @protected or @injected_user here because the callback needs to be able to post here for responses
@apfell.route(apfell.config['API_BASE'] + "/responses/<tid:int>", methods=['POST'])
async def update_task_for_callback(request, tid):
    data = request.json
    decoded = base64.b64decode(data['response']).decode("utf-8")
    try:
        task = await db_objects.get(Task, id=tid)
    except Exception as e:
        return json({'status': 'error',
                     'error': 'Task does not exist'})
    try:
        if 'response' not in data:
            return json({'status': 'error', 'error': 'task response not in data'})
        # the process is a little bit different if we're going to save things to disk, like a file or a screenshot instead of saving it into the database
        if task.command.cmd == "download" or task.command.cmd == "screencapture":
            try:
                download_response = js.loads(decoded)
                # print(download_response)
                if 'total_chunks' in download_response:
                    # print("creating file")
                    rsp = await create_filemeta_in_database_func(download_response)
                    if rsp['status'] == "success":
                        # update the response to indicate we've created the file meta data
                        rsp.pop('status', None)  # remove the status key from the dictionary
                        decoded = "Recieved meta data: " + js.dumps(rsp)
                        resp = await db_objects.create(Response, task=task, response=decoded)
                        task.status = "processed"
                        await db_objects.update(task)
                        status = {'status': 'success'}
                        resp_json = resp.to_json()
                        return json({**status, **resp_json, 'file_id': rsp['id']}, status=201)
                    else:
                        decoded = rsp['error']
                elif 'chunk_data' in download_response:
                    # print("storing chunk: " + str(download_response['chunk_num']))
                    print(download_response)
                    rsp = await download_file_to_disk_func(download_response)
                    if rsp['status'] == "success":
                        decoded = "Received chunk: " + str(rsp['chunk'])
                    else:
                        decoded = rsp['error']
            except Exception as e:
                print("error when trying to handle a download command: " + str(e))
                pass
        resp = await db_objects.create(Response, task=task, response=decoded)
        task.status = "processed"
        await db_objects.update(task)
        status = {'status': 'success'}
        resp_json = resp.to_json()
        return json({**status, **resp_json}, status=201)
    except Exception as e:
        print(e)
        return json({'status': 'error',
                     'error': 'Failed to update task',
                     'msg': str(e)})
