from contextlib import contextmanager
import os
from urllib import parse as urlparse

import requests

class OctoClient:
    """
    Encapsulates communication with one OctoPrint instance
    """

    def __init__(self, *, url=None, apikey=None, session=None):
        """
        Initialize the object with URL and API key

        If a session is provided, it will be used (mostly for testing)
        """
        if not url:
            raise TypeError('Required argument \'url\' not found or emtpy')
        if not apikey:
            raise TypeError('Required argument \'apikey\' not found or emtpy')

        parsed = urlparse.urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            raise TypeError('Provided URL is not HTTP(S)')
        if not parsed.netloc:
            raise TypeError('Provided URL is empty')

        self.url = '{}://{}'.format(parsed.scheme, parsed.netloc)

        self.session = session or requests.Session()
        self.session.headers.update({'X-Api-Key': apikey})

        # Try a simple request to see if the API key works
        # Keep the info, in case we need it later
        self.version = self.version()

    def _get(self, path, params=None):
        """
        Perform HTTP GET on given path with the auth header

        Path shall be the ending part of the URL,
        i.e. it should not be full URL

        Raises a RuntimeError when not 20x OK-ish

        Returns JSON decoded data
        """
        url = urlparse.urljoin(self.url, path)
        response = self.session.get(url, params=params)
        self._check_response(response)

        return response.json()

    def _post(self, path, data=None, files=None, json=None, ret=True):
        """
        Perform HTTP POST on given path with the auth header

        Path shall be the ending part of the URL,
        i.e. it should not be full URL

        Raises a RuntimeError when not 20x OK-ish

        Returns JSON decoded data
        """
        url = urlparse.urljoin(self.url, path)
        response = self.session.post(url, data=data, files=files, json=json)
        self._check_response(response)

        if ret:
            return response.json()

    def _delete(self, path):
        """
        Perform HTTP DELETE on given path with the auth header

        Path shall be the ending part of the URL,
        i.e. it should not be full URL

        Raises a RuntimeError when not 20x OK-ish

        Returns nothing
        """
        url = urlparse.urljoin(self.url, path)
        response = self.session.delete(url)
        self._check_response(response)
    
    def _put(self, path, data=None, files=None, json=None, ret=True):
        """
        Perform HTTP PUT on given path with the auth header

        Path shall be the ending part of the URL,
        i.e. it should not be full URL

        Raises a RuntimeError when not 20x OK-ish

        Returns JSON decoded data
        """
        url = urlparse.urljoin(self.url, path)
        response = self.session.put(url, data=data, files=files, json=json)
        self._check_response(response)

        if ret:
            return response.json()

    def _patch(self, path, data=None, files=None, json=None, ret=True):
        """
        Perform HTTP PATCH on given path with the auth header

        Path shall be the ending part of the URL,
        i.e. it should not be full URL

        Raises a RuntimeError when not 20x OK-ish

        Returns JSON decoded data
        """
        url = urlparse.urljoin(self.url, path)
        response = self.session.patch(url, data=data, files=files, json=json)
        self._check_response(response)

        if ret:
            return response.json()

    def _check_response(self, response):
        """
        Make sure the response status code was 20x, raise otherwise
        """
        if not (200 <= response.status_code < 210):
            error = response.text
            msg = 'Reply for {} was not OK: {} ({})'
            msg = msg.format(response.url, error, response.status_code)
            raise RuntimeError(msg)
        return response

    def version(self):
        """
        Retrieve information regarding server and API version
        """
        return self._get('/api/version')

    def _prepend_local(self, location):
        if location.split('/')[0] not in ('local', 'sdcard'):
            return 'local/' + location
        return location

    def files(self, location=None):
        """
        Retrieve information regarding all files currently available and
        regarding the disk space still available locally in the system

        If location is used, retrieve information regarding the files currently
        available on the selected location and - if targeting the local
        location - regarding the disk space still available locally in the
        system

        If location is a file, retrieves the selected file''s information
        """
        if location:
            location = self._prepend_local(location)
            return self._get('/api/files/{}'.format(location))
        return self._get('/api/files')

    @contextmanager
    def _file_tuple(self, file):
        """
        Yields a tuple with filename and file object

        Expects the same thing or a path as input
        """
        mime = 'application/octet-stream'

        try:
            exists = os.path.exists(file)
        except:
            exists = False

        if exists:
            filename = os.path.basename(file)
            with open(file, 'rb') as f:
                yield (filename, f, mime)
        else:
            yield file + (mime,)
    
    def files_info(self, location, filename):
        """
        Retrieves the selected file’s or folder’s information.
        If the file is unknown, a 404 Not Found is returned.
        If the targeted path is a folder, by default only its direct children 
        will be returned. If recursive is provided and set to true, all 
        sub folders and their children will be returned too.
        On success, a 200 OK is returned, with a file information item as 
        the response body.
        """
        return self._get('/api/files/{}/{}'.format(location, filename))


    def upload(self, file, *, location='local',
               select=False, print=False, userdata=None):
        """
        Upload a given file
        It can be a path or a tuple with a filename and a file-like object
        """
        with self._file_tuple(file) as file_tuple:
            files = {'file': file_tuple}
            data = {'select': str(select).lower(), 'print': str(print).lower()}
            if userdata:
                data['userdata'] = userdata

            return self._post('/api/files/{}'.format(location),
                              files=files, data=data)

    def delete(self, location):
        """
        Delete the selected filename on the selected target

        Location is target/filename, defaults to local/filename
        """
        location = self._prepend_local(location)
        self._delete('/api/files/{}'.format(location))

    def select(self, location, *, print=False):
        """
        Selects a file for printing

        Location is target/filename, defaults to local/filename
        If print is True, the selected file starts to print immediately
        """
        location = self._prepend_local(location)
        data = {
            'command': 'select',
            'print': print,
        }
        self._post('/api/files/{}'.format(location), json=data, ret=False)
    
    def slice(self, location, slicer='cura', gcode=None, printer_profile=None, 
              profile=None, select=False, print=False):
        """
        Slices an STL file into GCODE. 
        Note that this is an asynchronous operation that 
        will take place in the background after the response 
        has been sent back to the client.

        TODO: ADD POSITION, PROFILE.*
        """
        location = self._prepend_local(location)
        data = {
            'command': 'slice',
            'slicer': slicer,
            'select': select,
            'print': print,
        }
        if not gcode == None:
            data['gcode'] = gcode
        if not printer_profile == None:
            data['printerProfile'] = printer_profile
        if not profile == None:
            data['profile'] = profile
        return self._post('/api/files/{}'.format(location), json=data, ret=False)
    
    def copy(self, location, dest):
        """
        Copies the file or folder to a new destination on the same location
        """
        location = self._prepend_local(location)
        data = {
            'command': 'copy',
            'destination': dest,
        }
        return self._post('/api/files/{}'.format(location), json=data, ret=False)
    
    def move(self, location, dest):
        """
        Moves the file or folder to a new destination on the same location
        """
        location = self._prepend_local(location)
        data = {
            'command': 'move',
            'destination': dest,
        }
        return self._post('/api/files/{}'.format(location), json=data, ret=False)

    def connection_info(self):
        """
        Retrieve the current connection settings, including information
        regarding the available baudrates and serial ports and the
        current connection state.
        """
        return self._get('/api/connection')

    def state(self):
        """
        A shortcut to get the current state.
        """
        return self.connection_info()['current']['state']

    def connect(self, *, port=None, baudrate=None,
                printer_profile=None, save=None, autoconnect=None):
        """
        Instructs OctoPrint to connect to the printer

        port: Optional, specific port to connect to. If not set the current
        portPreference will be used, or if no preference is available auto
        detection will be attempted.

        baudrate: Optional, specific baudrate to connect with. If not set
        the current baudratePreference will be used, or if no preference
        is available auto detection will be attempted.

        printer_profile: Optional, specific printer profile to use for
        connection. If not set the current default printer profile
        will be used.

        save: Optional, whether to save the request's port and baudrate
        settings as new preferences. Defaults to false if not set.

        autoconnect: Optional, whether to automatically connect to the printer
        on OctoPrint's startup in the future. If not set no changes will be
        made to the current configuration.
        """
        data = {'command': 'connect'}
        if port is not None:
            data['port'] = port
        if baudrate is not None:
            data['baudrate'] = baudrate
        if printer_profile is not None:
            data['printerProfile'] = printer_profile
        if save is not None:
            data['save'] = save
        if autoconnect is not None:
            data['autoconnect'] = autoconnect
        self._post('/api/connection', json=data, ret=False)

    def disconnect(self):
        """
        Instructs OctoPrint to disconnect from the printer
        """
        data = {'command': 'disconnect'}
        self._post('/api/connection', json=data, ret=False)

    def fake_ack(self):
        """
        Fakes an acknowledgment message for OctoPrint in case one got lost on
        the serial line and the communication with the printer since stalled.
        This should only be used in "emergencies" (e.g. to save prints), the
        reason for the lost acknowledgment should always be properly
        investigated and removed instead of depending on this "symptom solver".
        """
        data = {'command': 'fake_ack'}
        self._post('/api/connection', json=data, ret=False)

    def job_info(self):
        """
        Retrieve information about the current job (if there is one)
        """
        return self._get('/api/job')

    def print(self):
        """
        Starts the print of the currently selected file

        Use select() to select a file
        """
        data = {'command': 'start'}
        self._post('/api/job', json=data, ret=False)

    def pause(self):
        """
        Pauses/unpauses the current print job

        There must be an active print job for this to work
        """
        data = {'command': 'pause'}
        self._post('/api/job', json=data, ret=False)

    def restart(self):
        """
        Restart the print of the currently selected file from the beginning

        There must be an active print job for this to work and the print job
        must currently be paused
        """
        data = {'command': 'restart'}
        self._post('/api/job', json=data, ret=False)

    def cancel(self):
        """
        Cancels the current print job

        There must be an active print job for this to work
        """
        data = {'command': 'cancel'}
        self._post('/api/job', json=data, ret=False)

    def logs(self):
        """
        Retrieve information regarding all log files currently available
        and regarding the disk space still available in the system on the
        location the log files are being stored
        """
        return self._get('/api/logs')

    def delete_log(self, filename):
        """
        Delete the selected log file with name filename
        """
        self._delete('/api/logs/{}'.format(filename))

    def _hwinfo(self, url, **kwargs):
        """
        Helper method for printer(), tool(), bed() and sd()
        """
        params = {}
        if kwargs.get('exclude'):
            params['exclude'] = ','.join(kwargs['exclude'])
        if kwargs.get('history'):
            params['history'] = 'true'
        if kwargs.get('limit'):
            params['limit'] = kwargs['limit']
        return self._get(url, params=params)

    def printer(self, *, exclude=None, history=False, limit=None):
        """
        Retrieves the current state of the printer

        Returned information includes:

        * temperature information
        * SD state (if available)
        * general printer state

        Temperature information can also be made to include the printer's
        temperature history by setting the history argument.
        The amount of data points to return here can be limited using the limit
        argument.

        Clients can specify a list of attributes to not return in the response
        (e.g. if they don't need it) via the exclude argument.
        """
        return self._hwinfo('/api/printer', exclude=exclude,
                            history=history, limit=limit)

    def tool(self, *, history=False, limit=None):
        """
        Retrieves the current temperature data (actual, target and offset) plus
        optionally a (limited) history (actual, target, timestamp) for all of
        the printer's available tools.

        It's also possible to retrieve the temperature history by setting the
        history argument. The amount of returned history data points can be
        limited using the limit argument.
        """
        return self._hwinfo('/api/printer/tool',
                            history=history, limit=limit)

    def bed(self, *, history=False, limit=None):
        """
        Retrieves the current temperature data (actual, target and offset) plus
        optionally a (limited) history (actual, target, timestamp) for the
        printer's heated bed.

        It's also possible to retrieve the temperature history by setting the
        history argument. The amount of returned history data points can be
        limited using the limit argument.
        """
        return self._hwinfo('/api/printer/bed',
                            history=history, limit=limit)

    def home(self, axes=None):
        """
        Homes the print head in all of the given axes.
        Additional parameters are:

        axes: A list of axes which to home, valid values are one or more of
        'x', 'y', 'z'. Defaults to all.
        """
        axes = [a.lower()[:1] for a in axes] if axes else ['x', 'y', 'z']
        data = {'command': 'home', 'axes': axes}
        self._post('/api/printer/printhead', json=data, ret=False)

    def jog(self, x=None, y=None, z=None):
        """
        Jogs the print head (relatively) by a defined amount in one or more
        axes. Additional parameters are:

        x: Optional. Amount to jog print head on x axis, must be a valid
        number corresponding to the distance to travel in mm.

        y: Optional. Amount to jog print head on y axis, must be a valid
        number corresponding to the distance to travel in mm.

        z: Optional. Amount to jog print head on z axis, must be a valid
        number corresponding to the distance to travel in mm.
        """
        data = {'command': 'jog'}
        if x:
            data['x'] = x
        if y:
            data['y'] = y
        if z:
            data['z'] = z
        self._post('/api/printer/printhead', json=data, ret=False)

    def feedrate(self, factor):
        """
        Changes the feedrate factor to apply to the movement's of the axes.

        factor: The new factor, percentage as integer or float (percentage
        divided by 100) between 50 and 200%.
        """
        data = {'command': 'feedrate', 'factor': factor}
        self._post('/api/printer/printhead', json=data, ret=False)

    @classmethod
    def _tool_dict(cls, whatever):
        if isinstance(whatever, (int, float)):
            whatever = (whatever,)
        if isinstance(whatever, dict):
            ret = whatever
        else:
            ret = {}
            for n, thing in enumerate(whatever):
                ret['tool{}'.format(n)] = thing
        return ret

    def tool_target(self, targets):
        """
        Sets the given target temperature on the printer's tools.
        Additional parameters:

        targets: Target temperature(s) to set.
        Can be one number (for tool0), list of numbers or dict, where keys
        must match the format tool{n} with n being the tool's index starting
        with 0.
        """
        targets = self._tool_dict(targets)
        data = {'command': 'target', 'targets': targets}
        self._post('/api/printer/tool', json=data, ret=False)

    def tool_offset(self, offsets):
        """
        Sets the given temperature offset on the printer's tools.
        Additional parameters:

        offsets: Offset(s) to set.
        Can be one number (for tool0), list of numbers or dict, where keys
        must match the format tool{n} with n being the tool's index starting
        with 0.
        """
        offsets = self._tool_dict(offsets)
        data = {'command': 'offset', 'offsets': offsets}
        self._post('/api/printer/tool', json=data, ret=False)

    def tool_select(self, tool):
        """
        Selects the printer's current tool.
        Additional parameters:

        tool: Tool to select, format tool{n} with n being the tool's index
        starting with 0. Or integer.
        """
        if isinstance(tool, int):
            tool = 'tool{}'.format(tool)
        data = {'command': 'select', 'tool': tool}
        self._post('/api/printer/tool', json=data, ret=False)

    def extrude(self, amount):
        """
        Extrudes the given amount of filament from the currently selected tool

        Additional parameters:

        amount: The amount of filament to extrude in mm.
        May be negative to retract.
        """
        data = {'command': 'extrude', 'amount': amount}
        self._post('/api/printer/tool', json=data, ret=False)

    def retract(self, amount):
        """
        Retracts the given amount of filament from the currently selected tool

        Additional parameters:

        amount: The amount of filament to retract in mm.
        May be negative to extrude.
        """
        self.extrude(-amount)

    def flowrate(self, factor):
        """
        Changes the flow rate factor to apply to extrusion of the tool.

        factor: The new factor, percentage as integer or float
        (percentage divided by 100) between 75 and 125%.
        """
        data = {'command': 'flowrate', 'factor': factor}
        self._post('/api/printer/tool', json=data, ret=False)

    def bed_target(self, target):
        """
        Sets the given target temperature on the printer's bed.

        target: Target temperature to set.
        """
        data = {'command': 'target', 'target': target}
        self._post('/api/printer/bed', json=data, ret=False)

    def bed_offset(self, offset):
        """
        Sets the given temperature offset on the printer's bed.

        offset: Temperature offset to set.
        """
        data = {'command': 'offset', 'offset': offset}
        self._post('/api/printer/bed', json=data, ret=False)

    def sd_init(self):
        """
        Initializes the printer's SD card, making it available for use.
        This also includes an initial retrieval of the list of files currently
        stored on the SD card, so after issuing files(location=sd) a retrieval
        of the files on SD card will return a successful result.

        If OctoPrint detects the availability of a SD card on the printer
        during connection, it will automatically attempt to initialize it.
        """
        data = {'command': 'init'}
        self._post('/api/printer/sd', json=data, ret=False)

    def sd_refresh(self):
        """
        Refreshes the list of files stored on the printer''s SD card.
        Will raise a 409 Conflict if the card has not been initialized yet
        with sd_init().
        """
        data = {'command': 'refresh'}
        self._post('/api/printer/sd', json=data, ret=False)

    def sd_release(self):
        """
        Releases the SD card from the printer. The reverse operation to init.
        After issuing this command, the SD card won't be available anymore,
        hence and operations targeting files stored on it will fail.
        Will raise a 409 Conflict if the card has not been initialized yet
        with sd_init().
        """
        data = {'command': 'release'}
        self._post('/api/printer/sd', json=data, ret=False)

    def sd(self):
        """
        Retrieves the current state of the printer's SD card.

        If SD support has been disabled in OctoPrint's settings,
        a 404 Not Found is risen.
        """
        return self._get('/api/printer/sd')

    def gcode(self, command):
        """
        Sends any command to the printer via the serial interface.
        Should be used with some care as some commands can interfere with or
        even stop a running print job.

        command: A single string command or command separated by newlines
        or a list of commands
        """
        try:
            commands = command.split('\n')
        except AttributeError:
            # already an iterable
            commands = list(command)
        data = {'commands': commands}
        self._post('/api/printer/command', json=data, ret=False)

    def settings(self, settings=None):
        """
        Retrieves the current configuration of printer
        python dict format if argument settings is not given

        Saves provided settings in argument settings (if given)
        and retrieves new settings in python dict format
        Expects a python dict with the settings to change as request body.
        This can be either a full settings tree,
        or only a partial tree containing
        only those fields that should be updated.

        Data model described:
        http://docs.octoprint.org/en/master/api/settings.html#data-model
        http://docs.octoprint.org/en/master/configuration/config_yaml.html#config-yaml
        """
        if settings:
            return self._post('/api/settings', json=settings, ret=True)
        else:
            return self._get('/api/settings')
    
    def timelapse_list(self, unrendered=None):
        """
        Retrieve a list of timelapses and the current config.
        Returns a timelase list in the response body.

        Unrendered, if True also includes unrendered timelapse.
        """
        if unrendered:
            return self._get('/api/timelapse', params=unrendered)
        return self._get('/api/timelapse')
    
    def delete_timelapse(self, filename):
        """
        Delete the specified timelapse

        Requires user rights
        """
        self._delete('/api/timelapse/{}'.format(filename))
    
    def command_unrend_timelapse(self, name, command):
        """
        Current only supports to render the unrendered timelapse 
        name via the render command.

        Requires user rights.

        name - The name of the unrendered timelapse
        command – The command to issue, currently only render is supported
        """
        data = {
            'command': 'render',
        }
        return self._post('/api/timelapse/unrendered/{}'.format(name), json=data)

    # def change_timelapse_conf(self):
    #     """
    #     Save a new timelapse configuration to use for the next print.
    #     The configuration is expected as the request body.
    #     Requires user rights.

    #     TODO: setup timelapse configuration
    #     """
    #     return self._post('api/timelapse/')
    
    def lst_slicers(self):
        """
        Returns a list of all available slicing profiles for all 
        registered slicers in the system.

        Returns a 200 OK response with a Slicer list as the body
        upon successful completion.
        """
        return self._get('/api/slicing/')
    
    def lst_slicer_profiles(self, slicer):
        """
        Returns a list of all available slicing profiles for
        the requested slicer. Returns a 200 OK response with
        a Profile list as the body upon successful completion.
        """
        return self._get('/api/slicing/{}/profiles'.format(slicer))
    
    def get_slicer_profile(self, slicer, key):
        """
        Retrieves the specified profile from the system.

        Returns a 200 OK response with a full Profile as 
        the body upon successful completion.
        """
        return self._get('/api/slicing/{}/profiles/{}'.format(slicer, key))
    
    # def add_slicer_profile(self, slicer, key):
    #     """
    #     Adds a new slicing profile for the given slicer to the system.
    #     If the profile identified by key already exists, it will be overwritten.

    #     Expects a Profile as body.

    #     Returns a 201 Created and an abridged Profile in the body 
    #     upon successful completion.

    #     Requires admin rights.

    #     TODO: Create a profile body to send
    #     TODO: Make a OctoClient _put method
    #     """
    #     return self._put('/api/slicing/{}/profiles/{}'.format(slicer, key))

    def delete_slicer_profile(self, slicer, key):
        """
        Delete the slicing profile identified by key for the slicer slicer. 
        If the profile doesn’t exist, the request will succeed anyway.

        Requires admin rights.
        """
        return self._delete('/api/slicing/{}/profiles/{}'.format(slicer, key))
    
    def printer_profiles(self):
        """
        Retrieves a list of all configured printer profiles.
        """
        return self._get('/api/printerprofiles')
    
    # def add_printer_profile(self):
    #     """
    #     """
    #     return self._post('/api/printerprofiles')

    def delete_printer_profile(self, profile):
        """
        Deletes an existing printer profile by its profile identifier.

        If the profile to be deleted is the currently selected profile, 
        a 409 Conflict will be returned.
        """
        return self._delete('/api/printerprofiles/{}'.format(profile))
    
    def languages(self):
        """
        Retrieves a list of installed language packs.
        """
        return self._get('/api/languages')
    
    def delete_language(self, locale, pack):
        """
        Retrieves a list of installed language packs.
        """
        return self._delete('/api/languages/{}/{}'.format(locale, pack))

    def system_commands(self):
        """
        Retrieves all configured system commands.
        A 200 OK with a List all response will be returned.
        """
        return self._get('/api/system/commands')
    
    def source_system_commands(self, source):
        """
        Retrieves the configured system commands for the specified source.
        The response will contain a list of command definitions.
        """
        return self._get('/api/system/commands/{}'.format(source))

    def execute_system_command(self, source, action):
        """
        Execute the system command action defined in source.
        Example
        Restart OctoPrint via the core system command restart 
        (which is available if the server restart command is configured).

        Parameters:
            source – The source for which to list commands, 
            currently either core or custom
            action – The identifier of the command, action from its definition
        """
        return self._post('/api/system/commands/{}/{}'.format(source, action))

    def users(self):
        """
        Retrieves a list of all registered users in OctoPrint.

        Will return a 200 OK with a user list response as body.

        Requires admin rights.
        """
        return self._get('/api/users')
    
    def user(self, username):
        """
        Retrieves information about a user.

        Will return a 200 OK with a user record as body.

        Requires either admin rights or to be logged in as the user.
        """
        return self._get('/api/users/{}'.format(username))
    
    def add_user(self, name, password, active=False, admin=False):
        """
        Adds a user to OctoPrint.
        Expects a user registration request as request body.
        Returns a list of registered users on success, see Retrieve a list of users.
        Requires admin rights.

        JSON Params:
            name – The user’s name
            password – The user’s password
            active – Whether to activate the account (true) or not (false)
            admin – Whether to give the account admin rights (true) or not (false)
        """
        data = {
            'name': name,
            'password': password,
            'active': active,
            'admin', admin,
        }
        return self._post('/api/users', json=data)
    
    def delete_user(self, username):
        """
        Delete a user record.
        Returns a list of registered users on success, see Retrieve a list of users.
        Requires admin rights.

        Parameters:
            username – Name of the user to delete
        """
        return self._delete('/api/users/{}'.format(username))

    def user_settings(self, username):
        """
        Retrieves a user’s settings.
        Will return a 200 OK with a JSON object representing the user’s 
        personal settings (if any) as body.
        Requires admin rights or to be logged in as the user.

        Parameters:
            username - Name of the user to retrieve the settings for
        """
        return self._get('/api/users/{}/settings'.format(username))
    
    def regen_user_apikey(self, username):
        """
        Generates a new API key for the user.
        Does not expect a body. Will return the generated API key as apikey 
        property in the JSON object contained in the response body.
        Requires admin rights or to be logged in as the user.

        Parameters:
            username – Name of the user to retrieve the settings for
        """
        return self._post('/api/users/{}/apikey'.format(username))
    
    def delete_user_apikey(self, username):
        """
        Deletes a user’s personal API key.
        Requires admin rights or to be logged in as the user.

        Parameters:
            username – Name of the user to retrieve the settings for
        """
        return self._delete('/api/users/{}/apikey'.format(username))
    
    def wizard(self):
        """    
        Retrieves additional data about the registered wizards.

        Returns a 200 OK with an object mapping wizard identifiers to wizard 
        data entries.
        """
        return self._get('/setup/wizard')

    def finish_wizard(self, handled):
        """
        Inform wizards that the wizard dialog has been finished.

        Expects a JSON request body containing a property handled 
        which holds a list of wizard identifiers which were handled 
        (not skipped) in the wizard dialog.

        Will call octoprint.plugin.WizardPlugin.on_wizard_finish() 
        for all registered wizard plugins, supplying the information 
        whether the wizard plugin’s identifier was within the list of 
        handled wizards or not.
        """
        data = {
            'handled': handled,
        }
        return self._post('/setup/wizard', json=data)
