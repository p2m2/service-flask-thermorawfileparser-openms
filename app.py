from flask import Flask, render_template, request, jsonify, send_file
import docker
import tempfile
import shutil
from zipfile import ZipFile
import glob
import os

UPLOAD_FOLDER = '/tmp/'

## ===============================
## UPDATE HERE IMAGE
## ===============================
docker_image_thermorawfileparser = 'inraep2m2/thermorawfileparser:1.4.3'
docker_image_openms              = 'inraep2m2/openms:3.1.0-pre-nightly-2024-02-03'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

container = None
itnum=1
dirworkpath=None
diroutputpath=None 

format="mzML"

@app.route('/')
def index():
    return render_template('thermorawfileparser.html')

@app.route('/logs')
def logs():
    global container
    global itnum
    global diroutputpath
    global dirworkpath
    global format 

    if container is None:
        return jsonify(console="Waiting for Docker container ...",run=True)
    else:
        
        totall = "<h3><i>Docker console ({})</i></h3>".format(docker_image_thermorawfileparser)
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
            client = docker.from_env()
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
                print("-in=/data/{} --out=/output/{}".format(filename,filename_without_ext+"."+format))
                print("===========================")
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
                
            ## make archive
            if format !=  "mzML" :
                shutil.make_archive(app.config['UPLOAD_FOLDER']+'/data', 'zip', diroutputpath_withnewformat)
            else:
                shutil.make_archive(app.config['UPLOAD_FOLDER']+'/data', 'zip', diroutputpath)
                        
            # delete unuserd directories/files
            shutil.rmtree(diroutputpath_withnewformat)
            shutil.rmtree(diroutputpath)
            shutil.rmtree(dirworkpath)
            
            container = None
            itnum=1
            dirworkpath=None
            diroutputpath=None 
            
    
        return jsonify(console=totall,run=run)

@app.route('/download_results')
def download_results():
    return send_file(app.config['UPLOAD_FOLDER']+'/data.zip', as_attachment=True)
     

@app.route('/process', methods=['POST'])
def process():
    # Handle form submission and file processing here
    if request.method == "POST":
        global format

        file = request.files['file']
        format = request.form['format']
        print(file)
        print(format)
        global dirworkpath
        dirworkpath = tempfile.mkdtemp()

        
        file.save(dirworkpath + "/" + file.filename)
        
        print(dirworkpath + "/" + file.filename)

        # unzip if needed
        if file.filename.endswith(".zip"):
            with ZipFile(dirworkpath + "/" + file.filename, 'r') as f:
                f.extractall(dirworkpath)

        print("** work directory **")
        print(glob.glob(dirworkpath+"/*"))

        global diroutputpath
        diroutputpath = tempfile.mkdtemp()
        
        global container
        # Crée un client Docker
        
        client = docker.from_env()
        client.images.pull( docker_image_thermorawfileparser)

        container = client.containers.run(docker_image_thermorawfileparser,
                            "--input_directory=/data/ --output=/output/",                            
                            volumes={
                                dirworkpath : {'bind': '/data/', 'mode': 'rw'},
                                diroutputpath : {'bind': '/output/', 'mode': 'rw'}
                                },
                            detach=True,
                            remove=True)
        ### debugging
        #stream = container.logs(stream=True)
        #for i in stream:
        #    print(i.decode("utf-8")) 

    return render_template('thermorawfileparser.html')

if __name__ == '__main__':
    app.run(debug=True)