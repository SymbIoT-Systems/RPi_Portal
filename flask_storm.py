from flask import Flask, render_template, redirect
from os.path import expanduser
from flask.ext.stormpath import StormpathManager,login_required,groups_required,user,current_user,current_app
from stormpath.client import Client
import time


# Global Variables

## dd/mm/yyyy format
today = time.strftime("%Y-%m-%d")

server_date = {
'server_date': str(today)
# 'server_date':'2014-11-21'
}


# Stormpath Initialisations and config
api_key_file = '~/.stormpath/apiKey.properties'
client = Client(api_key_file_location = expanduser(api_key_file))



app = Flask(__name__)
app.config['SECRET_KEY'] = 'xxx'
app.config['STORMPATH_API_KEY_FILE'] = expanduser('~/.stormpath/apiKey.properties')
app.config['STORMPATH_APPLICATION'] = 'BITS-Testbed'

#Disable Middle Name as an input while registering
app.config['STORMPATH_ENABLE_MIDDLE_NAME'] = False
#Enable User name so that we can use either username/email for login
# app.config['STORMPATH_ENABLE_USERNAME'] = True
app.config['STORMPATH_ENABLE_SURNAME'] = False
app.config['STORMPATH_ENABLE_GIVEN_NAME'] = False


stormpath_manager = StormpathManager(app)

#href for BITS-Testbed
href = 'https://api.stormpath.com/v1/applications/49g4BErzwiMOORfvPwGbRI'
application = client.applications.get(href)

href_dir = 'https://api.stormpath.com/v1/directories/49g8VIABIcpbMy63mu4R9s'
directory = client.directories.get(href_dir)

# directory = client.directories.search({'name': 'BITS-Testbed Default'})[0]

# cluster_no = 1

# viewer = directory.groups.create({'name': 'viewer'})

viewer_list = directory.groups.search({'name': 'viewer*'})
viewer_group1 = False
viewer_group2 = False

for grp in viewer_list:
	if grp.name == "viewer1":
		viewer_group1 = grp

	elif grp.name == "viewer2":
		viewer_group2 = grp

# # accounts = application.accounts.search({'email': user.email})
# accounts = application.accounts.search({'email': 'symbiotsystems@gmail.com'})

# account = False
# for acc in accounts:
#     account = acc

valid_groups = []
valid_groups.append('admins')
viewer_list = directory.groups.search({'name': 'viewer*'})
for group in viewer_list:
	valid_groups.append(group)

print valid_groups

@app.route('/')
def home():
	if current_user.is_authenticated():
		print user.email
		return render_template('index.html')

	else:
		errorMessage= {
            'error' : 'You are not logged in!!'
        }
		return render_template('error.html',**errorMessage)

@app.route('/admins')
@groups_required(['admins'])
def admins():
	return "Kuch kaam kar le :P"

@app.route('/reserve')
@login_required
def reserve():
	
	reservation_valid = True
	if reservation_valid == True:
		print "Reservation is valid"
		
		member_viewer = False
		group_memberships = user.group_memberships
		for gms in group_memberships:

			if 'viewer' in gms.group.name:
				member_viewer = True
				print "Already a viewer!"
				pass
			
		if member_viewer == False:
			user.add_group(viewer_group1)
			# viewer_group1.add_account(user.email)
			member_viewer = True


	return render_template('reserve.html',**server_date)

@app.route('/reservation_done')
@login_required
def res_done():
	print "Reservation Done!"

	return render_template('waiting.html',**server_date)

@app.route('/dashboard')
@groups_required(valid_groups, all=False)
def dashboard():
	return "<html><head>You have reached the control panel! Grab a cookie!</head></br><body><a href="+'/signout'+' class="formButton" '+'title="Logout"'+'>Logout</a></body></html>'
	

@app.route('/signout')
def logout():
	print "Logging out!"
	group_memberships = user.group_memberships
	
	for gms in group_memberships:
	    # print gms.account.given_name
	    if 'viewer' in gms.group.name:
	    	gms.delete()

	return redirect('/logout')


if __name__ == '__main__':
  app.run('0.0.0.0',port=8080,debug=True)