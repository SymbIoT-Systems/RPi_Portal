import sqlite3
import json
conn=sqlite3.connect('portal.db')
cursor=conn.execute('SELECT * FROM RESERVATIONS')
a=cursor.fetchone()
z=(a[3].split(','))
new=[]
for i in z:
	new.append(int(i))
print type(new[0])
print new
conn.close()