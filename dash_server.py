'''
Web application to interact with the WSN Testbed. 
Features:

1.Ping all nodes
2.Upload tos_image.xml files
3.Listen mode: Basestation sniffer and show output in a console online
4.Switch images on all nodes and show image details of current slot after switching
5.Detect changes in port,status of basestation plugged into laptop
6.Read basestation's contents in the eeprom slots
'''

import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, Response, send_file, make_response
from werkzeug import secure_filename
import serial
from flask.ext.socketio import SocketIO, emit
from time import sleep
import subprocess
import sys
import json
import sqlite3
import re #String replacements
import mosquitto, os, urlparse
from gevent import monkey
monkey.patch_all()

#Global variable declarations

templateData = {
    'consoledata':"Nothing yet"+"\n",
    'baseimagedata':"BaseStation offline"+"\n",
    'flashstarted' : "False"
}

slotnum = 1
imagepath = "uploads/"

# Initialize the Flask application
app = Flask(__name__)
app.debug=True

#Code uploading
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = set(['xml'])

#Packet sniffing
app.config['SECRET_KEY']="secret!"
socketio=SocketIO(app)
listenrequest=False

#Database initialisation
file_status = os.path.isfile('portal.db')

if (file_status == False):
    conn = sqlite3.connect('portal.db')
    conn.execute('''CREATE TABLE NODEDETAILS 
        (ID INTEGER PRIMARY KEY AUTOINCREMENT,
        NODE_NUM    INT NOT NULL,
        DEV_ID    TEXT,
        NODE_TYPE   TEXT,
        SPECIAL_PROP    TEXT,
        BATTERY_STATUS  TEXT );''')
    conn.execute('''CREATE TABLE CLUSTERDETAILS
        (ID INTEGER PRIMARY KEY AUTOINCREMENT,
            CLUSTER_NO INT NOT NULL,
            HEAD_NO INT NOT NULL,
            HEAD_DEVICEID TEXT,
            NODE_LIST TEXT NOT NULL,
            PI_MAC TEXT,
            PI_IP TEXT,
            SLOT1 TEXT,
            SLOT2 TEXT,
            SLOT3 TEXT);''')
    conn.close()

    

#Function Definitions
#MQTT Functions
def on_connect(mosq, obj, rc):
    print("rc: " + str(rc))

def on_message(mosq, obj, msg):
    print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
    if msg.topic == "response/1":
    	if "usbbasepath" in str(msg.payload):
    		# here send data to frontend
    		socketio.emit('usbbasepath',str(msg.payload).replace("usbbasepath",""),namespace="/templatedata")
    	elif "ping" in str(msg.payload):
    		status=json.loads(str(msg.payload).replace("ping ",''))
    		return json.dumps(status)
    	elif "switch" in str(msg.payload):
			return json.dumps(str(msg.payload).replace("switch ",""))
        elif "flash" in str(msg.payload):
            return str(msg.payload).replace("flash ","")
        elif "ackreceived" in str(msg.payload):
            global templatedata
            templateData['consoledata']="Nothing yet"
            return str(msg.payload).replace("ackreceived ","")
    elif msg.topic == "listen/1":
    	print str(msg.payload)


def on_publish(mosq, obj, mid):
    print("mid: " + str(mid))

def on_subscribe(mosq, obj, mid, granted_qos):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))

def on_log(mosq, obj, level, string):
    print(string)

# For a given file, return whether it's an allowed type or not
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

#MQTT Events
mqttc = mosquitto.Mosquitto()
# Assign event callbacks
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_publish = on_publish
mqttc.on_subscribe = on_subscribe

url_str = 'mqtt://localhost:1883'
url = urlparse.urlparse(url_str)
mqttc.connect(url.hostname, url.port)

#Channels to subscribe
mqttc.subscribe("response/1", 0)
mqttc.subscribe("listen/1", 0)

#App routes         
@app.route('/')
def index():
    mqttc.publish("commands/1","usbbasepath")
    return render_template('dashboard.html',**templateData)

@app.route('/cluster_status/',methods=['POST'])
def pingall():
    imagenum=request.form['data']
    mqttc.publish("commands/1","ping "+imagenum)
    
@app.route('/switch/', methods=['POST'])
def switch():
    if request.method == "POST":
        imagenum = request.form['imagenumberswitch']
        mqttc.publish("commands/1","switch "+imagenum)  

# Route that will process the file upload
@app.route('/upload', methods=['POST'])
def upload():
    global imagepath,slotnum
    slotnum=request.form['imagenumber']

    # Get the name of the uploaded file
    file = request.files['file']
    # Check if the file is one of the allowed types/extensions
    if file and allowed_file(file.filename):
        # Make the filename safe, remove unsupported chars
        filename = secure_filename(file.filename)
        imagepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(imagepath)

    global templateData
    templateData['flashstarted']="True"
    f = open(imagepath)
    datastring = f.read()
    byteArray = bytes(datastring)
    mqttc.publish("files/1", byteArray ,0)
    return redirect('/')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               filename,as_attachment=True)

@app.route('/flashnode/', methods=['POST'])
def flashnode():
    global slotnum
    mqtt.publish("commands/1","flash "+slotnum)
    templateData['flashstarted']="False"

@app.route('/startlisten/',methods=['POST'])
def startlisten():
    
    publish("commands/1","startlisten")
    return "Listen Start Done"    

@app.route('/savelog/',methods=['POST'])
def savedata():
    log_file=open(app.config['UPLOAD_FOLDER']+request.form['filename'],"w")
    log_data = request.form['filedata']
    log_data1=((log_data.replace("<p>","\n")).replace("</p>","")).replace("<br>","\n")
    log_file.write(log_data1)
    log_file.close()
    #return redirect(url_for('uploaded_file',filename="log.txt"))
    return "Uploaded"

@app.route('/stoplisten/',methods=['POST'])
def stoplisten():
    mqttc.publish("commands/1","stoplisten")
    return "0"


@app.route('/ackreceived/',methods=['POST'])
def ackreceived():
	mqttc.publish("commands/1","ackreceived")

@app.route('/data_manage/')
def data_manage():
    return render_template('data_manage.html')

@app.route('/data_add/', methods=['POST'])
def data_add():
    table=request.form['data']
    conn = sqlite3.connect('portal.db')
    if table == "nodeadd":
        nodeid=(request.form['nodeid'])
        dev_id=(request.form['dev_id'])
        node_prop=request.form['nodeprop']
        node_type=request.form['nodetype']
        # conn.execute("INSERT INTO NODESTATUS (NODE_NUM, CLUSTER_HEAD, NODE_TYPE, SPECIAL_PROP) VALUES (%d,%d,\'%s\',\'%s\')" % (int(request.form['nodeid']), int(request.form['clusterh_id']),request.form['nodetype'],request.form['nodeprop']))
        conn.execute("INSERT INTO NODEDETAILS (NODE_NUM, DEV_ID, NODE_TYPE, SPECIAL_PROP) VALUES (" + nodeid + ",'" + dev_id + "','" + node_type + "','" + node_prop + "')")
    elif table == "clusteradd":
        clusterno=request.form['clusterno']
        clusterhead_no=request.form['clusterhead_no']
        head_dev_id=request.form['head_dev_id']
        node_list=request.form['node_list']
        gateway_mac=request.form['gateway_mac']
        gateway_ip=request.form['gateway_ip']
        conn.execute("INSERT INTO CLUSTERDETAILS (CLUSTER_NO,HEAD_NO,HEAD_DEVICEID,NODE_LIST,PI_MAC,PI_IP) VALUES (" +clusterno + "," + clusterhead_no + ",'" + head_dev_id + "','" + node_list + "','" + gateway_mac + "','" + gateway_ip + "')")
    conn.commit()
    conn.close()
    return '0'

@app.route('/data_get/',methods=['POST'])
def data_get():
    table=request.form['data']
    conn = sqlite3.connect('portal.db')
    if table == "nodesdata":
        cursor=conn.execute("SELECT * from NODEDETAILS")
        a = cursor.fetchall()
    elif table == "clustersdata":
        cursor=conn.execute("SELECT * from CLUSTERDETAILS")
        a = cursor.fetchall()
    print a
    conn.close()
    # print "after"+a
    return json.dumps(a)

@app.route('/data_edit/',methods=['POST'])
def data_edit():
    conn = sqlite3.connect('portal.db')
    idno=(request.form['idno'])
    table=request.form['data']
    if table == "nodeedit":
        nodeid=(request.form['nodeid'])
        dev_id=(request.form['dev_id'])
        node_prop=request.form['nodeprop']
        node_type=request.form['nodetype']
        conn.execute("UPDATE NODEDETAILS SET NODE_NUM = "+nodeid+" ,DEV_ID = "+dev_id+", NODE_TYPE = '"+node_type+"', SPECIAL_PROP = '" + node_prop + "' WHERE ID="+ idno +";")
        print "done"
    elif table == "clusteredit":
        clusterno=request.form['clusterno']
        clusterhead_no=request.form['clusterhead_no']
        head_dev_id=request.form['head_dev_id']
        node_list=request.form['node_list']
        gateway_mac=request.form['gateway_mac']
        gateway_ip=request.form['gateway_ip']
        conn.execute("UPDATE CLUSTERDETAILS SET CLUSTER_NO = " + clusterno + ",HEAD_NO = "+ clusterhead_no +",HEAD_DEVICEID = '"+ head_dev_id +"',NODE_LIST = '" + node_list + "',PI_MAC = '" + gateway_mac + "',PI_IP = '" + gateway_ip+"' WHERE ID="+ idno +";")
    conn.commit()
    conn.close()
    return "Done"


#NOT REDUNDANT!
@socketio.on('listen',namespace='/listen')
def handle_message(message):
    print('received message: ' + message)


if __name__ == '__main__':
    socketio.run(app,host='0.0.0.0',port=8088)
    # Continue the network loop, exit when an error occurs
    rc = 0
    while rc == 0:
        rc = mqttc.loop()
    print("rc: " + str(rc))



