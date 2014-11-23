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
from time import sleep,strftime
import subprocess
#from pyudev import Context, Monitor, MonitorObserver, Device
import sys
import json
import sqlite3
import re #String replacements
import mosquitto, os, urlparse
from gevent import monkey
monkey.patch_all()
import paho.mqtt.client as mqtt
import zlib
import unicodedata
from os.path import expanduser
from flask.ext.stormpath import StormpathManager,login_required,groups_required,user,current_user,current_app
from stormpath.client import Client
import threading
from datetime import datetime,date

#Global variable declarations
server_date = {
'server_date': str(date.today()),
'email':"dummy"
# 'server_date':'2014-11-21'
}


templateData = {
    'consoledata':"Nothing yet"+"\n",
    'baseimagedata':"BaseStation offline"+"\n",
    'flashstarted' : "False",
    'cluster_number':1,
    'admin':"False",
    'email':"dummy"
}

slotnum = 1
imagepath = "uploads/"

#Stormpath and Flask initialisations
api_key_file = '~/.stormpath/apiKey.properties'
client = Client(api_key_file_location = expanduser(api_key_file))

app = Flask(__name__)
app.debug = True

app.config['SECRET_KEY'] = 'xxx'
app.config['STORMPATH_API_KEY_FILE'] = expanduser('~/.stormpath/apiKey.properties')
app.config['STORMPATH_APPLICATION'] = 'BITS-Testbed'

#Disable Middle Name as an input while registering
app.config['STORMPATH_ENABLE_MIDDLE_NAME'] = False
#Enable User name so that we can use either username/email for login
# app.config['STORMPATH_ENABLE_USERNAME'] = True
app.config['STORMPATH_ENABLE_SURNAME'] = False
app.config['STORMPATH_ENABLE_GIVEN_NAME'] = False

#Code uploading
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['ALLOWED_EXTENSIONS'] = set(['xml'])

#Packet sniffing
app.config['SECRET_KEY']="secret!"
socketio=SocketIO(app)
listenrequest=False

stormpath_manager = StormpathManager(app)

#hrefs for BITS-Testbed Application and Account Store Directory
href = 'https://api.stormpath.com/v1/applications/49g4BErzwiMOORfvPwGbRI'
application = client.applications.get(href)

href_dir = 'https://api.stormpath.com/v1/directories/49g8VIABIcpbMy63mu4R9s'
directory = client.directories.get(href_dir)

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
    conn.execute('''CREATE TABLE RESERVATIONS
        (ID INTEGER PRIMARY KEY AUTOINCREMENT,
            USEREMAIL TEXT NOT NULL,
            DATE_RESERVED TEXT NOT NULL,
            SLOTNUMBERS TEXT NOT NULL,
            CLUSTERNUMBER TEXT NOT NULL,
            USEROBJECT TEXT NOT NULL);''')
    conn.close()

    

#Function Definitions

#MQTT Functions
def on_connect(mosq, obj, rc):
    print("rc: " + str(rc))

def on_message(mosq, obj, msg):
    print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
    if "response/" in msg.topic:
        if "usbbasepath" in str(msg.payload):
            # here send data to frontend
            sleep(2)
            socketio.emit('usbbasepath',str(msg.payload).replace("usbbasepath",""),namespace="/listen")
        elif "ping" in str(msg.payload):
            status=json.loads(str(msg.payload).replace("ping ",''))
            socketio.emit('ping',json.dumps(status),namespace="/listen")
        elif "switch" in str(msg.payload):
            status=json.loads(str(msg.payload).replace("switch ",''))
            socketio.emit('switch',json.dumps(status),namespace="/listen")
        elif "flash" in str(msg.payload):
            status=json.loads(str(msg.payload).replace("flash ",''))
            socketio.emit('flash',json.dumps(status),namespace="/listen")
        elif "ackreceived" in str(msg.payload):
            global templateData
            templateData['consoledata']="Nothing yet"
            socketio.emit('ackreceived',str(msg.payload).replace("ackreceived ",""),namespace="/listen")
        elif "batterystatus" in str(msg.payload):
            status=json.loads(str(msg.payload).replace("batterystatus ",''))
            socketio.emit('batterystatus',json.dumps(status),namespace="/listen")           
            
    elif "listen/" in msg.topic:
        socketio.emit('my response',str(msg.payload),namespace="/listen")
    elif msg.topic == "register":
        database=json.loads(str(msg.payload))
        conn=sqlite3.connect('portal.db')
        cursor=conn.execute("SELECT * FROM CLUSTERDETAILS WHERE PI_MAC='"+database['Gatewaymac']+"';")
        a=cursor.fetchall()
        listofnodes=a[0][4]
        conn.execute("UPDATE CLUSTERDETAILS SET PI_IP = \'" + database['Gatewayip'] +"\', SLOT1=\'"+database['Progname1'] +"\', SLOT2=\'"+database['Progname2'] +"\', SLOT3=\'"+database['Progname3'] +"\' WHERE ID="+ str(a[0][0]) +";")
        conn.commit()
        registerresponse={
            'clusterid':a[0][1],
            'listofnodes':listofnodes
        }
        mqttc.publish('register_response',json.dumps(registerresponse))
        mqttc.subscribe("response/"+str(a[0][1]), 0)
        mqttc.subscribe("listen/"+str(a[0][1]), 0)
        conn.close()

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
#mqttc = mosquitto.Mosquitto("python_pub")
mqttc = mqtt.Client()
# Assign event callbacks
mqttc.on_message = on_message
mqttc.on_connect = on_connect
#mqttc.on_publish = on_publish
mqttc.on_subscribe = on_subscribe

url_str = 'mqtt://localhost:1883'
url = urlparse.urlparse(url_str)
mqttc.connect(url.hostname, url.port)

#Channels to subscribe
mqttc.subscribe("register",0)
mqttc.loop_start()

#List of groups 
valid_groups_dash = ['admins']

viewer_list = directory.groups.search({'name': 'viewer*'})
viewer_group1 = False
viewer_group2 = False

for grp in viewer_list:
    valid_groups_dash.append(grp)

    if grp.name == "viewer1":
        viewer_group1 = grp

    elif grp.name == "viewer2":
        viewer_group2 = grp

admins=directory.groups.search({'name':'admins'})
admin = False
for grp in admins:
    admin = grp

waitings=directory.groups.search({'name':'waiting'})
waiting = False
for grp in waitings:
    waiting = grp


def check_reservations():
    conn=sqlite3.connect('portal.db')
    cursor = conn.execute('SELECT * FROM RESERVATIONS WHERE DATE_RESERVED=\''+str(date.today())+'\'')
    allcursor=cursor.fetchall()
    for everyelement in allcursor:
        slots=everyelement[3].split(',')
        for slot in slots:
            if slot==str((datetime.now().hour)+1):#In hours
                print "My slot"
                if everyelement[4] == "1":
                    try:
                        viewer_group1.add_account(everyelement[1])
                    except:
                        print "Already exists"
                elif everyelement[4] == "2":
                    try:
                        viewer_group2.add_account(everyelement[1])
                    except:
                        print "Already exists"
                try:
                    group_memberships = user.group_memberships
    
                    for gms in group_memberships:
                        if 'waiting' in gms.group.name:
                            gms.delete()
                except:
                    print "Cannot delete error"

    conn.close()

# Background timing thread
#Change to 1 minute or greater
def bg_timer():
    check_reservations()
    threading.Timer(5.0, bg_timer).start()

bg_timer()

def validate(value):
    listofgroups=[]
    groups_member=user.group_memberships
    clusterreq=0
    for gms in groups_member:
        listofgroups.append(gms.group.name)
    if "admins" in listofgroups:
        clusterreq=value
    elif "viewer1" in listofgroups:
        clusterreq=1
    elif "viewer2" in listofgroups:
        clusterreq=2
    return clusterreq


#App routes         
@app.route('/')
def home():

    if current_user.is_authenticated():
        print user.email
        return redirect ('/waiting')

    else:
        return render_template('index.html')

@app.route('/admins')
@groups_required(['admins'])
def admins():
    return "Kuch kaam kar le :P"

@app.route('/reserve')
@login_required
def reserve():
    # if not current_user.is_authenticated():
    #     print "You are not logged in!"
             
    #     errorMessage= {
    #         'error' : 'You are not logged in!!'
    #     }

    #     return render_template('error.html',**errorMessage)

    # reservation_valid = True

    # if reservation_valid == True:
    #     print "Reservation is valid"
        
    #     member_viewer = False
    #     group_memberships = user.group_memberships
    #     for gms in group_memberships:

    #         if 'viewer' in gms.group.name:
    #             member_viewer = True
    #             print "Already a viewer!"
    #             pass
            
    #     if member_viewer == False:
    #         user.add_group(viewer_group1)
    #         # viewer_group1.add_account(user.email)
    #         member_viewer = True
            
        return render_template('reserve.html',**server_date)

@app.route('/reserve_slot/',methods=['POST'])
@login_required
def reserve_slot():
    date=request.form['date']
    clusternumber=request.form['clusternumber']
    slots=request.form['slots']
    if slots == "":
        return "Reservation not complete"
    conn=sqlite3.connect('portal.db')
    emailaddress=unicodedata.normalize('NFKD', user.email).encode('ascii','ignore')
    conn.execute('INSERT INTO RESERVATIONS (USEREMAIL,DATE_RESERVED,SLOTNUMBERS,CLUSTERNUMBER,USEROBJECT) VALUES (\''+(emailaddress)+'\',\''+str(date)+'\',\''+str(slots)+'\',\''+clusternumber+'\',\''+str(user)+'\')')
    conn.commit()
    conn.close()
    try:
        user.add_group('waiting')
    except:
        print "Already in group"
    check_reservations()
    return "Reservation Done!"

@app.route('/delete_slot/',methods=['POST'])
@login_required
def delete_slot():
    date=request.form['date']
    clusternumber=request.form['clusternumber']
    slots=request.form['slots']
    if slots=="":
        return "Please choose a slot to delete"
    conn=sqlite3.connect('portal.db')
    cursor=conn.execute('SELECT * FROM RESERVATIONS WHERE USEREMAIL=\''+str(user.email)+'\' AND DATE_RESERVED=\''+date+'\' AND CLUSTERNUMBER=\''+clusternumber+'\'')
    allcursor=cursor.fetchall()
    slotsdelete=slots.split(',')
    for everyelement in allcursor:
        slotsnew=[]
        slotsreserved=everyelement[3].split(',')
        for sr in slotsreserved:
            for sd in slotsdelete:
                if str(sr) == str(sd):
                    pass
                else:
                    slotsnew.append(sr)
        conn.execute('UPDATE RESERVATIONS SET SLOTNUMBERS=\''+','.join(slotsnew)+'\' WHERE ID=\''+everyelement[0]+'\'')
    conn.commit()
    conn.close()
    return "Slot deleted"

@app.route('/waiting')
@login_required
def waiting():
    allowedtostay=False
    group_memberships=user.group_memberships
    for gms in group_memberships:
        if (gms.group.name == "waiting") or ("viewer" in gms.group.name) or (gms.group.name == "admins"):
            allowedtostay=True
    if allowedtostay == False:
        return redirect('/reserve')
    elif allowedtostay == True:
        print "Reservation Done!"
        server_date['email']=str(user.email).split('@')[0]
        return render_template('waiting.html',**server_date)
        

@app.route('/signout')
def logout():
    print "Logging out!"
    group_memberships = user.group_memberships
    
    for gms in group_memberships:
        # print gms.account.given_name
        if 'viewer' in gms.group.name:
            gms.delete()

    return redirect('/logout')

@app.route('/dashboard/')
@login_required
# @groups_required(valid_groups_dash, all=False)
def index():
    entry_allowed = False
    group_memberships = user.group_memberships
    for gms in group_memberships:
        for i in valid_groups_dash:
            if str(gms.group.name) == str(i):
                entry_allowed = True
        if gms.group.name == "admins":
            templateData['admin']=True
        elif gms.group.name == "viewer1":
            templateData['cluster_number']=1
        elif gms.group.name == "viewer2":
            templateData['cluster_number']=2
    if entry_allowed == True:
        mqttc.publish("commands/1","usbbasepath")
        templateData['email']=str(user.email).split('@')[0]
        return render_template('dashboard.html',**templateData)
        
    else:
        errorMessage = {
            'error' : 'You are not allowed here!...yet.'
        }
        return render_template('error.html',**errorMessage)

@app.route('/cluster_status/',methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def pingall():
    imagenum=request.form['data']

    mqttc.publish("commands/"+str(validate(request.form['clusterid'])),"ping "+str(imagenum))
    return "0"

@app.route('/switch/', methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def switch():
    if request.method == "POST":
        imagenum = request.form['imagenumberswitch']
        mqttc.publish("commands/"+str(validate(request.form['clusterid'])),"switch "+str(imagenum))  
        return "0"

# Route that will process the file upload
@app.route('/upload', methods=['POST'])
@groups_required(valid_groups_dash,all = False)
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
    return redirect('/dashboard/')

@app.route('/uploads/<filename>')
@groups_required(valid_groups_dash,all = False)
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               filename,as_attachment=True)

@app.route('/flashnode/', methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def flashnode():
    global slotnum
    f = open(imagepath)
    datastring = f.read()
    byteArray = bytes(datastring)
    checksum = zlib.crc32(datastring, 0xFFFF)
    print "Checksum is: " + str(checksum)
    clusterreq=str(validate(request.form['clusterid']))
    mqttc.publish("files/"+clusterreq, byteArray ,0)
    mqttc.publish("commands/"+clusterreq, "checksum "+str(checksum))
    mqttc.publish("commands/"+clusterreq,"flash "+str(slotnum))
    templateData['flashstarted']="False"
    return "0"

@app.route('/startlisten/',methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def startlisten():
    mqttc.publish("commands/"+str(validate(request.form['clusterid'])),"startlisten")
    return "Listen Start Done"    

@app.route('/savelog/',methods=['POST'])
@login_required
def savedata():
    log_file=open(app.config['UPLOAD_FOLDER']+request.form['filename'],"w")
    log_data = request.form['filedata']
    log_data1=((log_data.replace("<p>","\n")).replace("</p>","")).replace("<br>","\n")
    log_file.write(log_data1)
    log_file.close()
    #return redirect(url_for('uploaded_file',filename="log.txt"))
    return "Uploaded"

@app.route('/stoplisten/',methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def stoplisten():
    mqttc.publish("commands/"+str(validate(request.form['clusterid'])),"stoplisten")
    return "0"


@app.route('/ackreceived/',methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def ackreceived():
    mqttc.publish("commands/"+str(validate(request.form['clusterid'])),"ackreceived")
    return "0"

@app.route('/data_manage/')
@groups_required(['admins'])
def data_manage():
    return render_template('data_manage.html')

@app.route('/data_add/', methods=['POST'])
@groups_required(['admins'])
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
@groups_required(['admins'])
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
@groups_required(['admins'])
def data_edit():
    conn = sqlite3.connect('portal.db')
    idno=(request.form['idno'])
    table=request.form['data']
    if table == "nodeedit":
        nodeid=(request.form['nodeid'])
        dev_id=(request.form['dev_id'])
        node_prop=request.form['nodeprop']
        node_type=request.form['nodetype']
        conn.execute("UPDATE NODEDETAILS SET NODE_NUM = "+nodeid+" ,DEV_ID = '"+dev_id+"', NODE_TYPE = '"+node_type+"', SPECIAL_PROP = '" + node_prop + "' WHERE ID="+ idno +";")
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

@app.route('/data_delete/',methods=['POST'])
@groups_required(['admins'])
def data_delete():
    conn=sqlite3.connect('portal.db')
    idno=request.form['idno']
    deletewhat=request.form['deletewhat']
    if deletewhat == "node":
        conn.execute("DELETE FROM NODEDETAILS WHERE ID=\'"+idno+"\'")
    elif deletewhat == "cluster":
        conn.execute("DELETE FROM CLUSTERDETAILS WHERE ID=\'"+idno+"\'")
    conn.commit()
    conn.close()
    return "Data Entry Deleted"

@app.route('/clusterdetails/',methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def clusterdetails():
    clusternumbers=[]
    clusternum=request.form['data']
    conn=sqlite3.connect('portal.db')
    cursor=conn.execute("SELECT * FROM CLUSTERDETAILS")
    first=[]    
    if clusternum == "dummydata":
        first=cursor.fetchone()
        clusternumbers.append(str(first[1]))
        remaining=cursor.fetchall()
        for i in remaining:
            clusternumbers.append(str(i[1]))
    else:
        allvalues=cursor.fetchall()
        for i in allvalues:
            clusternumbers.append(str(i[1]))
            if str(i[1]) == clusternum:
                first=i
    datareturn={
        'clusternumbers':','.join(clusternumbers),
        'listofnodes':first[4],
        'slot1':first[7],
        'slot2':first[8],
        'slot3':first[9]
    }
    conn.close()

    return json.dumps(datareturn)


@app.route('/add_registration/',methods=['POST'])
@groups_required(valid_groups_dash,all = False)
def add_registration():
    useremail=request.form['useremail']
    date=request.form['date_reserved']
    slots=request.form['slot_numbers']
    clusternum=request.form['cluster_number']
    conn=sqlite3.connect('portal.db')
    conn.execute('INSERT INTO RESERVATIONS (USEREMAIL,DATE_RESERVED,SLOTNUMBERS,CLUSTERNUMBER) VALUES (\''+useremail+'\',\''+date+'\',\''+slots+'\',\''+clusternum+'\'')
    conn.commit()
    conn.close()
    return "Reservation Done"

@app.route('/get_registration/',methods=['POST'])
@login_required
def get_registration():
    clusternumbers=[]
    date=request.form['date_reserved']
    clusternum=request.form['cluster_number']
    whichpage = request.form['pagename']
    conn=sqlite3.connect('portal.db')
    cursor=conn.execute('SELECT * FROM RESERVATIONS WHERE DATE_RESERVED=\''+date+'\' AND CLUSTERNUMBER=\''+clusternum+'\'')
    allcursor=cursor.fetchall()
    slotsreserved=[]
    slotsreservedforme=[]
    
    min_slot = 25
    delta = 0

    if whichpage == 'waiting':
        for everyelement in allcursor:
            if user.email == everyelement[1]:
                # Check for next valid slot for this user
                list_el= everyelement[3].split(',')
                for i in list_el:
                    if ((int(i)- datetime.now().hour) >= 1):
                        if min_slot > int(i):
                            min_slot = int(i)
                            print i
                slotsreservedforme.append(str(everyelement[3]))
            else:
                slotsreserved.append(str(everyelement[3]))
    elif whichpage == 'reserve':
        for everyelement in allcursor:
            slotsreserved.append(str(everyelement[3]))
    if min_slot != 25:
        delta_hour=(min_slot-datetime.now().hour-2)    
        delta_min=60-(datetime.now().minute)
        delta_sec=60-(datetime.now().second)

        delta = delta_sec+60*delta_min+3600*delta_hour
        print "time"+str(delta_hour)

    elif min_slot == 25:
        delta = 90000

    cursor1=conn.execute("SELECT * FROM CLUSTERDETAILS")
    allvalues=cursor1.fetchall()
    for i in allvalues:
        clusternumbers.append(str(i[1]))
        if str(i[1]) == clusternum:
            first=i
    conn.close()
    #For current slot
    if delta < 0:
        delta=0
    return json.dumps({'slotsreserved':','.join(slotsreserved),'listofnodes':first[4],'clusternumbers':clusternumbers,'slotsreservedforme':','.join(slotsreservedforme),'next_slot_delta':delta})

#NOT REDUNDANT!
@socketio.on('listen',namespace='/listen')
@groups_required(valid_groups_dash,all = False)
def handle_message(message):
    print('received message: ' + message)

if __name__ == '__main__':
    socketio.run(app,host='0.0.0.0',port=8088)