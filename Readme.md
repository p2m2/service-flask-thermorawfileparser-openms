
## service-flask-thermorawfileparser-openms

[![Static Badge](https://img.shields.io/badge/orion_inrae-openstack-blue)](https://services-p2m2-test-192-168-100-66.vm.openstack.genouest.org)
[![Static Badge](https://img.shields.io/badge/genostack_genouest-openstack-blue)](https://services-p2m2-test-192-168-100-66.vm.openstack.genouest.org)


A simple HTML interface for converting RAW format to MzML, MzXML, and MGF files.

### Install

```bash
python3 -m venv env
. env/bin/activate
pip3 install flask docker python-dotenv
```

### Configuration

Edit `.flaskenv` to configure the Flask environment variables.

### Run service

```bash
. .venv/bin/activate
flask run
```

Visit `http://{host}:{port}/` to access the service.


## Docker images

### inraep2m2/Dockerfile_thermorawfileparser

version : ThermoRawFileParser1.4.3.zip

#### Build and push image

```bash
docker build . -f Dockerfile_thermorawfileparser -t inraep2m2/thermorawfileparser:1.4.3
docker login --username=p2m2
docker image push inraep2m2/thermorawfileparser:1.4.3
```

#### Usage

```bash
raw data is localized in $PWD/data directory
docker run -v $PWD/data:/data -t inraep2m2/thermorawfileparser:1.4.3 -i=/data/MM_NOx_1_Direct.raw
```

### inraep2m2/openms

[Original Dockerfile](https://raw.githubusercontent.com/OpenMS/dockerfiles/master/executables/Dockerfile)


#### Build and push image
```bash
docker build . -f Dockerfile_openms -t inraep2m2/openms:3.1.0-pre-nightly-2024-02-03
docker login --username=p2m2
docker image push inraep2m2/openms:3.1.0-pre-nightly-2024-02-03
```

#### Usage

```bash
raw data is localized in $PWD/data directory
docker run -v $PWD/data:/data -it inraep2m2/openms:3.1.0-pre-nightly-2024-02-03 FileConverter -in /data/MM_NOx_1_Direct.mzML -out /data/MM_NOx_1_Direct.mzXML
```
