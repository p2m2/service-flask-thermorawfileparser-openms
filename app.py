from flask import Flask, render_template, request, jsonify, send_file
import docker
import tempfile
import shutil
from zipfile import ZipFile

UPLOAD_FOLDER = '/tmp/'
ALLOWED_EXTENSIONS = {'zim', 'raw', 'mzML', 'mzXML', 'tar', 'gz'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

container = None
itnum=1
dirworkpath=None
diroutputpath=None 

@app.route('/')
def index():
    return render_template('thermorawfileparser.html')

@app.route('/logs')
def logs():
    global container
    global itnum
    global diroutputpath
    global dirworkpath
    
    if container is None:
        return jsonify(console="Waiting for Docker container ...",run=True)
    else:
        
        totall = ""
        try:
            # Hack to simulate printing asynchronously
            
            stream = container.logs(stream=True)
            for i in range(itnum):
                totall += next(stream).decode("utf-8") 
            run = True
            itnum+=1
        except:
            
            run = False
                    
            shutil.make_archive(app.config['UPLOAD_FOLDER']+'/data', 'zip', diroutputpath)
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
    print("###########PROCESS")
    if request.method == "POST":
        file = request.files['file']
        format = request.form['format']
        print(file)
        print(format)
        global dirworkpath
        dirworkpath = tempfile.mkdtemp()

        
        file.save(dirworkpath + "/" + file.filename)
        
        # unzip if needed
        if file.filename.endswith(".zip"):
            with ZipFile(dirworkpath + "/" + file.filename, 'r') as f:
                f.extractall(dirworkpath)

        
        global diroutputpath
        diroutputpath = tempfile.mkdtemp()
        
        #print(dirworkpath)
        #print(diroutputpath)

        global container
        # Crée un client Docker
        
        client = docker.from_env()
        client.images.pull( 'inraep2m2/thermorawfileparser:1.4.3')

        container = client.containers.run('inraep2m2/thermorawfileparser:1.4.3',
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
