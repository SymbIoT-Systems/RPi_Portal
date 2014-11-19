from flask import Flask, render_template
from os.path import expanduser
from flask.ext.stormpath import StormpathManager,login_required,groups_required

app = Flask(__name__)
app.config['SECRET_KEY'] = 'xxx'
app.config['STORMPATH_API_KEY_FILE'] = expanduser('~/.stormpath/apiKey.properties')
app.config['STORMPATH_APPLICATION'] = 'BITS-Testbed'

#Disable Middle Name as an input while registering
app.config['STORMPATH_ENABLE_MIDDLE_NAME'] = False
# app.config['STORMPATH_ENABLE_SURNAME'] = False
# app.config['STORMPATH_ENABLE_GIVEN_NAME'] = False
stormpath_manager = StormpathManager(app)



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
  return render_template('reserve.html')

@app.route('/dashboard')
@groups_required(['viewer', 'admins'], all=False)
def dashboard():
	return "You have reached the control panel! Grab a cookie!"

if __name__ == '__main__':
  app.run('0.0.0.0',port=8080,debug=True)