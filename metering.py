# -*- coding: utf-8 -*-

from influxdb import InfluxDBClient
from influxdb import SeriesHelper
import subprocess
import json
import requests

# Set up project names here
projects = ['minio-test']

# InfluxDB connections settings
host = 'localhost'
port = 8086
user = 'root'
password = 'root'
dbname = 'mydb'

myclient = InfluxDBClient(host, port, user, password, dbname)

# Uncomment the following code if the database is not yet created
myclient.create_database(dbname)
myclient.create_retention_policy('metering_policy', '60d', 3, default=True)


class MySeriesHelper(SeriesHelper):
    """Instantiate SeriesHelper to write points to the backend."""

    class Meta:
        """Meta class stores time series helper configuration."""

        # The client should be an instance of InfluxDBClient.
        client = myclient

        # The series name must be a string. Add dependent fields/tags
        # in curly brackets.
        series_name = 'usage.stats.{project_name}'

        # Defines all the fields in this time series.
        fields = ['namespace', 'cpu', 'mem', 'storage', 'pvc']

        # Defines all the tags for the series.
        tags = ['project_name']

        # Defines the number of data points to store prior to writing
        # on the wire.
        bulk_size = 5

        # autocommit must be set to True when using bulk_size
        autocommit = True

def query_openshift() -> None:
    for this_project in projects:
        cpu_size = 0; mem_size = 0
        print('USING PROJECT:', this_project)
        cpu_size, mem_size = generate_report(this_project)
        print('CPU (mCPU):', cpu_size)
        print('MEM (MiB):', mem_size)
        pvc_size = generate_pvc_report(this_project)
        print('PVC (GiB):', pvc_size)
        image_size = generate_imagestream_report(this_project)
        print('Image (MiB):', image_size)
        MySeriesHelper(project_name=this_project, cpu=cpu_size, mem=mem_size, storage=image_size, pvc=pvc_size)

def generate_report(namespace) -> int:
    cpu_size = 0; mem_size = 0
    cmd = "/root/oc " + "adm top pods --namespace " + namespace
    nodata = "No resources found"
    output = subprocess.run([cmd], shell=True, text=True, capture_output=True)
    z = json.dumps(output.__dict__).split()
#    print("stdout:", output.stdout)
#    print("stderr:", output.stderr)
#    print("z value", output)

    if nodata in output.stderr:
        print("No pod resources found")
        return(cpu_size, mem_size)

    # Position list pointer on first and last pod name by looking for two known strings
    start = z.index('MEMORY(bytes)') + 1
    end = z.index('"stderr":') - 4
#    print(z[start:end])
    i=start
    while i <= end:
        # Remove the first two chars of the pod name
        pod_raw=z[i]
        pod_clean=pod_raw[2:]
        # Write the time series to the InfluxDB database
        cpu_raw = z[i+1]
        cpu_size = cpu_size + int(cpu_raw[:-1])
        mem_raw = z[i+2]
        mem_size = mem_size + int(mem_raw[:-2])
        # Bump the list pointer by three to position it on next pod
        i = i+3

    return(cpu_size, mem_size)

def generate_pvc_report(namespace) -> int:
    i = 2; size_int = 0
    cmd = "/root/oc " + "get pvc --namespace " + namespace + " -o custom-columns=pvc:.metadata.name,storage:.spec.resources.requests.storage"
    output = subprocess.run([cmd], shell=True, text=True, capture_output=True)

    list =  output.stdout.split()

    if len(list) <= 2:
#       print("No PVC resources found")
       return(size_int)

    # Position list pointer on first pvc name
    while i < len(list):
        # print(f'{namespace} {list[i]} {list[i+1]}')
        # Sumup the pvc sizes
        raw_size = list[i+1]
        # Remove last two chars which contain the Gi
        size_int = size_int + int(raw_size[:-2])
        # Bump the list pointer to position it on next pvc - if there is one
        i = i+2

    return(size_int)

def generate_imagestream_report(namespace) -> float:
    i = 4; size_float = 0.0
    # Use imagestreams rather than images - although, maybe we need both?
    cmd = "/root/oc " + "adm top imagestreams --namespace " + namespace
    output = subprocess.run([cmd], shell=True, text=True, capture_output=True)

    list =  output.stdout.split()

    if len(list) <= 2:
       print("No image resources found")
       return(size_float)

    # Position list pointer on first image name
    while i < len(list):
        # print(f'{namespace} {list[i]} {list[i+1]}')
        # Sumup the image sizes
        raw_size = list[i+1]
        # If not just a byte value (B), remove last three chars which contain the 'MiB'
        if raw_size[-2] != 'i':
            i = i+4
            continue

        # print('image::', raw_size)
        size_float = size_float + float(raw_size[:-3])
        # Bump the list pointer to position it on next image - if there is one
        i = i+4

    return(size_float)


def main():
    print("Starting Metering Analysis")
    print("==========================")

    query_openshift()

    # To manually submit data points which are not yet written, call commit:
    MySeriesHelper.commit()

    # To inspect the JSON which will be written, call _json_body_():
    MySeriesHelper._json_body_()

if __name__ == "__main__":
    main()
