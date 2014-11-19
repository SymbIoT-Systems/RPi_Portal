from flask import Flask, render_template
from os.path import expanduser
from flask.ext.stormpath import StormpathManager,login_required,groups_required,user
from stormpath.client import Client

# Not working :\
#
api_key_file = '~/.stormpath/apiKey.properties'
client = Client(api_key_file_location = expanduser(api_key_file))



app = Flask(__name__)
app.config['SECRET_KEY'] = 'xxx'
app.config['STORMPATH_API_KEY_FILE'] = expanduser('~/.stormpath/apiKey.properties')
app.config['STORMPATH_APPLICATION'] = 'BITS-Testbed'

#Disable Middle Name as an input while registering
app.config['STORMPATH_ENABLE_MIDDLE_NAME'] = False
#Enable User name so that we can use either username/email for login
app.config['STORMPATH_ENABLE_USER_NAME'] = True

app.config['STORMPATH_ENABLE_SURNAME'] = False
app.config['STORMPATH_ENABLE_GIVEN_NAME'] = False

stormpath_manager = StormpathManager(app)

#href for BITS-Testbed
href = 'https://api.stormpath.com/v1/applications/49g4BErzwiMOORfvPwGbRI'
application = client.applications.get(href)


href_dir = 'https://api.stormpath.com/v1/directories/49g8VIABIcpbMy63mu4R9s'
directory = client.directories.get(href_dir)
# default_account_store_mapping = client.applications.get(href_dir)

# cluster_no = 1
# href_grp = 'https://api.stormpath.com/v1/groups/4GCbAPCu3GXeHGrb2EWFt2'
# viewer = client.groups.get(href)
# viewer = directory.groups.search({'name': 'viewer'})
# accounts = application.accounts.search({'email': 'symbiotsystems@gmail.com'})
accounts = application.accounts.search({'given_name': 'SymbIoT'})
account = False
for acc in accounts:
    account = acc

print account    
# viewer = directory.groups.create({'name': 'viewer'})

groups = directory.groups.search({'name': 'viewer'})
group = False
for grp in groups:
    group = grp

@app.route('/')
def home():

  return render_template('index.html')

@app.route('/admins')
@groups_required(['admins'])
def admins():
	return "Kuch kaam kar le :P"


@app.route('/reserve')
@login_required
def reserve():
	#reservation successful
	reservation_valid = True

	if reservation_valid == True:
		print "Hello"
		accounts = application.accounts.search({'given_name': 'SymbIoT'})
		account = False
		for acc in accounts:
		    account = acc

		# user.groups.add(viewer)
		groups = account.groups
		for grp in groups:
			if grp.name == 'viewer':
				pass
			else:
				group.add_account(account)	    
		

	return render_template('reserve.html')

@app.route('/dashboard')
@groups_required(['viewer', 'admins'], all=False)
def dashboard():
	return "You have reached the control panel! Grab a cookie!"

if __name__ == '__main__':
  app.run('0.0.0.0',port=8080,debug=True)