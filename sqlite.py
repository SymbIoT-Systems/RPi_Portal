import sqlite3
import json
conn=sqlite3.connect('portal.db')
cursor=conn.execute('SELECT * FROM CLUSTERDETAILS')
a=cursor.fetchall()
print json.dumps(a)