from flask import Flask, render_template, request, jsonify, send_file, session
from flask_session import Session
from cachelib.file import FileSystemCache

import docker
import tempfile
import shutil
from zipfile import ZipFile
import glob
import os

## ===============================
## UPDATE HERE IMAGE
## ===============================
docker_image_thermorawfileparser = 'inraep2m2/thermorawfileparser:1.4.3'
docker_image_openms              = 'inraep2m2/openms:3.1.0-pre-nightly-2024-02-03'

app = Flask(__name__)

app.config['SECRET_KEY'] = 'oh_so_secret'
SESSION_TYPE = 'cachelib'
SESSION_SERIALIZATION_FORMAT = 'json'
SESSION_CACHELIB = FileSystemCache(threshold=500, cache_dir=f"{os.path.dirname(__file__)}/sessions")
app.config.from_object(__name__)

Session(app)
client = docker.from_env()
        
def get_session(container_id):
    idx = session['containers'].index(container_id)
    if idx >=0 and idx < len(session['containers']):
        return session['containers'][idx]
    else: 
        None

def remove_session(container_id):
    try:
        idx = session['containers'].index(container_id)
        if idx >=0 and idx < len(session['containers']):
            session['containers'].pop(idx)
    except:
        pass

def set_session(container_id,current_session):
    if 'containers' not in session :
        session['containers'] = []
        
    remove_session(container_id)
    session['containers'].append(current_session)


@app.route('/')
def index():
    return render_template('thermorawfileparser.html',container_id="test....")

@app.route('/logs/<container_id>')
def logs(container_id):
    if container_id == None :
        return "Error Devel Session. container_id missing. "
    
    container = client.containers.get(container_id)
    session = get_session(container_id)

    itnum = session['iternum']
    diroutputpath = session['diroutputpath']
    dirworkpath = session['dirworkpath']
    format = session['format']

    if container is None:
        return jsonify(console="Waiting for Docker container ...",run=True)
    else:
        
        totall = "<h3><i>Docker console ({})</i></h3>".format(docker_image_thermorawfileparser)
        totall += "Format:{}<br/>".format(format)
        totall += "Docker id:{}<br/>".format(container.id)
        try:
            # Hack to simulate printing asynchronously
            
            stream = container.logs(stream=True)
            for i in range(itnum):
                totall += next(stream).decode("utf-8") 
            run = True
            itnum+=1
        except:
            
            run = False
            ## load openms to convert file
            client.images.pull( docker_image_openms ) 
            diroutputpath_withnewformat = tempfile.mkdtemp()

            ## Hack change Voc MS:1003145 (ThermoRawFileParser to MsConvert) to MS:1000615
            
            totall = "<h3><i>Hack W4M</i></h3>"
            totall += "MS:1003145 (ThermoRawFileParser) -> MS:1000615 (MsConvert)<br/>"

            for file in glob.glob(diroutputpath+"/*.mz*"):
                   
                with open(file, 'r') as f:
                    filedata = f.read()
                    f.close()
                
                filedata = filedata.replace('MS:1003145', 'MS:1000615')
                
                os.remove(file)

                # Write the file out again
                with open(file, 'w') as f:
                    f.write(filedata)
                    f.close()
                    totall+='<span style="color:red;">' + file.split("/")[-1] + "</span><br/>"
                
                filename = os.path.basename(file)
                filename_without_ext = os.path.splitext(filename)[0]
                
                if format !=  "mzML" :
                    totall = "<h3>Docker console ({})</h3>".format(docker_image_openms)
                    totall += '<span style="color:green;">' + (client.containers.run(docker_image_openms,
                                "FileConverter -in /data/{} -out /output/{}".format(filename,filename_without_ext+"."+format),                            
                                volumes={
                                     diroutputpath : {'bind': '/data/', 'mode': 'rw'},
                                     diroutputpath_withnewformat : {'bind': '/output/', 'mode': 'rw'},
                                },
                                detach=False,
                                remove=False)).decode("utf-8").replace("\n","<br/>") +"</span><br/>"
            
            import uuid

            result_zip_file_tmp = "data_"+str(uuid.uuid4()) 
        
            ## make archive
            if format !=  "mzML" :
                shutil.make_archive(result_zip_file_tmp, 'zip', diroutputpath_withnewformat)
            else:
                shutil.make_archive(result_zip_file_tmp, 'zip', diroutputpath)
            

            result_zip_file=result_zip_file_tmp+".zip"
            print(glob.glob(result_zip_file+"*"))

            # delete unused directories/files
            shutil.rmtree(diroutputpath_withnewformat)
            shutil.rmtree(diroutputpath)
            shutil.rmtree(dirworkpath)
            session = {
                'container'       : None,
                'itnum'           : 1,
                'dirworkpath'     : None,
                'diroutputpath'   : None, 
                'result_zip_file' : result_zip_file,
                'format'          : format 
            }
            
            set_session(container_id,session)
            return jsonify(console=totall,run=run)
        
        #print("*************************************")
        #if container != None:
        #    session['container']   = str(container.id)
        #else:
        #    session['container']   = None
        #print(session['container'])
        #print("*************************************")
        #session['iternum']         = itnum
        #session['dirworkpath']     = dirworkpath
        #session['diroutputpath']   = diroutputpath 
        #session['format']          = format

        return jsonify(console=totall,run=run)

@app.route('/download_results/<container_id>')
def download_results(container_id):
    if container_id == None :
        return "Error Devel Session. container_id missing. "
    
    result_zip_file = session['result_zip_file']
    print(result_zip_file)    
    if (result_zip_file != None):
        return send_file(result_zip_file, as_attachment=True)
    else:
        return render_template('thermorawfileparser.html')

@app.route('/process/', methods=['GET','POST'])
def process():
    # Handle form submission and file processing here
    if request.method == "POST":
        file = request.files['file']
        format = request.form['format']
    
        dirworkpath = tempfile.mkdtemp()

        file.save(dirworkpath + "/" + file.filename)
        
        # unzip if needed
        if file.filename.endswith(".zip"):
            with ZipFile(dirworkpath + "/" + file.filename, 'r') as f:
                f.extractall(dirworkpath)

        diroutputpath = tempfile.mkdtemp()
        
        # Crée un client Docker
        client.images.pull( docker_image_thermorawfileparser)

        container = client.containers.run(docker_image_thermorawfileparser,
                            "--input_directory=/data/ --output=/output/",                            
                            volumes={
                                dirworkpath : {'bind': '/data/', 'mode': 'rw'},
                                diroutputpath : {'bind': '/output/', 'mode': 'rw'}
                                },
                            detach=True,
                            remove=True)

        print("*******************************************") 
        print(str(container.id))
        print(client.containers.get(container.id))
        #print(client.containers.list(filters={'id': container.id}))
        print("*******************************************") 
        
        session = {}
        container_id = str(container.id)
        session['container']       = container_id
        session['iternum']         = 1
        session['dirworkpath']     = dirworkpath
        session['diroutputpath']   = diroutputpath 
        session['result_zip_file'] = None 
        session['format']          = format

        set_session(container_id,session)
        ### debugging
        #stream = container.logs(stream=True)
        #for i in stream:
        #    print(i.decode("utf-8")) 
        print(container_id)
    print("RETTTTTTTTT")
    return render_template('thermorawfileparser.html',container_id=container_id)

if __name__ == '__main__':
    app.run(debug=True)