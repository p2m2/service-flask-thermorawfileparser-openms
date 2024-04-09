from flask import Flask, render_template, request, jsonify, send_file, session, abort
from flask_session import Session
from cachelib.file import FileSystemCache

import docker
import tempfile
import shutil
from zipfile import ZipFile
import glob
import os
import time

## ===============================
## UPDATE HERE IMAGE
## ===============================
docker_image_thermorawfileparser = 'inraep2m2/thermorawfileparser:1.4.3'
docker_image_openms              = 'inraep2m2/openms:3.1.0-pre-nightly-2024-02-03'

retentiontime_downloadable_resultfile_in_second=14400 #-> 4h

app = Flask(__name__)

app.config['SECRET_KEY'] = 'oh_so_secret'
SESSION_TYPE = 'cachelib'
SESSION_SERIALIZATION_FORMAT = 'json'
SESSION_CACHELIB = FileSystemCache(threshold=1000, cache_dir=f"{os.path.dirname(__file__)}/sessions")
app.config.from_object(__name__)

Session(app)

client = docker.from_env()
client.images.pull(docker_image_thermorawfileparser)
client.images.pull(docker_image_openms) 

path_download_dir="download_data"

if not os.path.exists(path_download_dir):
    os.mkdir(path_download_dir)

def get_session(container_id):
    return next(item for item in session['containers'] if (item['container_id'] == container_id))
 

def remove_session(container_id):
    session['containers']=[x for x in session['containers'] if not (container_id == x.get('container_id'))]


def set_session(container_id,current_session):
    if 'containers' not in session :
        session['containers'] = []
        
    remove_session(container_id)
    session['containers'].append(current_session)

@app.route('/')
def index():
    return render_template('thermorawfileparser.html')

@app.route('/logs/<container_id>')
def logs(container_id):
     
    if container_id == None :
        totall = "[logs/<container_id>]Error Devel Session. container_id is missing. "
        return jsonify(console=totall,run=False)
    
    totall = "<h3><i>Docker console ({})</i></h3>".format(docker_image_thermorawfileparser)
  
    try:
        my_session = get_session(container_id)
    except StopIteration:
        # Session is not save...waiting for
        totall+="<i>running docker instance....</i><br>"
   
        return jsonify(console=totall,run=True)

    iternum = my_session['iternum']
    diroutputpath = my_session['diroutputpath']
    dirworkpath = my_session['dirworkpath']
    format = my_session['format']

    totall += "Format:{}<br/>".format(format)
    totall += "Docker id:{}<br/>".format(container_id)

    try:
        container = client.containers.get(container_id)
        # Hack to simulate printing asynchronously
        
        stream = container.logs(stream=True)
        for i in range(iternum):
            totall += next(stream).decode("utf-8") 
        run = True
        iternum+=1
        
        my_session_update = {
            'container_id'    : container_id,
            'iternum'         : iternum,
            'dirworkpath'     : dirworkpath,
            'diroutputpath'   : diroutputpath, 
            'result_zip_file' : None,
            'format'          : format,
            'timestamp'       : my_session['timestamp']
        }
    except :
        container = None
        run = False
        
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

        result_zip_file_tmp = path_download_dir+"/data_"+str(uuid.uuid4()) 
    
        ## make archive
        if format !=  "mzML" :
            shutil.make_archive(result_zip_file_tmp, 'zip', diroutputpath_withnewformat)
        else:
            shutil.make_archive(result_zip_file_tmp, 'zip', diroutputpath)
        
        result_zip_file=result_zip_file_tmp+".zip"

        # delete unused directories/files
        shutil.rmtree(diroutputpath_withnewformat)
        shutil.rmtree(diroutputpath)
        shutil.rmtree(dirworkpath)
        
        my_session_update = {
            'container_id'    : container_id,
            'iternum'         : 1,
            'dirworkpath'     : None,
            'diroutputpath'   : None, 
            'result_zip_file' : result_zip_file,
            'format'          : format,
            'timestamp'       : my_session['timestamp']
        }
        
    set_session(container_id,my_session_update)
    return jsonify(console=totall,run=run)

@app.route('/download_results/<container_id>')
def download_results(container_id):

    if container_id == None :
        abort(404)

    my_session = get_session(container_id)
    
    result_zip_file = my_session['result_zip_file']
    
    if (result_zip_file != None):
        return send_file(result_zip_file, as_attachment=True)
    else:
        abort(404)

@app.route('/process/', methods=['GET','POST'])
def process():
    # remove if sesion if date creation is to old. try to remove files/directories if exist    
    if 'containers' in session:
        clean_sessions=[]
        for old_session in session['containers']:
            print(int(time.time() - old_session['timestamp']) )
            if (int(time.time() - old_session['timestamp'])
                  <retentiontime_downloadable_resultfile_in_second):
                clean_sessions.append(old_session)
            else:
                print(old_session)
                if old_session['result_zip_file'] != None:
                    try:
                        os.remove(old_session['result_zip_file'])
                    except:
                        pass
                if old_session['dirworkpath'] != None:
                    try:
                        shutil.rmtree(old_session['dirworkpath'])
                    except:
                        pass
                if old_session['diroutputpath'] != None:
                    try:
                        shutil.rmtree(old_session['diroutputpath'])
                    except:
                        pass

        session['containers']=clean_sessions

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

        #print(glob.glob(dirworkpath+"/*"))
        # hack if the zip is a directory containing files
        for f in glob.glob(dirworkpath+"/**/*.raw", recursive=True):
            if not os.path.exists(dirworkpath+"/"+f.split("/").pop()):
                shutil.move(f,dirworkpath)

        diroutputpath = tempfile.mkdtemp()
        
        # Crée un client Docker
        

        container = client.containers.run(docker_image_thermorawfileparser,
                            "--input_directory=/data/ --output=/output/",                            
                            volumes={
                                dirworkpath : {'bind': '/data/', 'mode': 'rw'},
                                diroutputpath : {'bind': '/output/', 'mode': 'rw'}
                                },
                            detach=True,
                            remove=True)        

        container_id = str(container.id)

        my_session = {
                'container_id'    : container_id,
                'iternum'         : 1,
                'dirworkpath'     : dirworkpath,
                'diroutputpath'   : diroutputpath, 
                'result_zip_file' : None,
                'format'          : format,
                'timestamp'       : time.time() 
            }
        
        set_session(container_id,my_session)
    
    return render_template('console.html',container_id=container_id)

if __name__ == '__main__':
    app.run(debug=True)