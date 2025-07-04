import serial
import logging
import re
import threading
import time
from time import sleep

def remove_crud(string):
    """Return string without useless information.
     Return string with trailing zeros after a decimal place, trailing
     decimal points, and leading and trailing spaces removed.
     """
    if "." in string:
        string = string.rstrip('0')

    string = string.lstrip('0 ')
    string = string.rstrip(' .')

    return string

def convert_units(val, fromUnit, toUnit):
    """ Convert flowrate units. Possible volume values: ml, ul, pl; possible time values: hor, min, sec
    :param fromUnit: unit to convert from
    :param toUnit: unit to convert to
    :type fromUnit: str
    :type toUnit: str
    :return: float
    """
    time_factor_from = 1
    time_factor_to = 1
    vol_factor_to = 1
    vol_factor_from = 1

    if fromUnit[-3:] == "sec":
        time_factor_from = 60
    elif fromUnit == "hor": # does it really return hor?
        time_factor_from = 1/60
    else:
        pass

    if toUnit[-3:] == "sec":
        time_factor_to = 1/60
    elif toUnit[-3:] == "hor":
        time_factor_to = 60
    else:
        pass

    if fromUnit[:2] == "ml":
        vol_factor_from = 1000
    elif fromUnit[:2] == "nl":
        vol_factor_from = 1/1000
    elif fromUnit[:2] == "pl":
        vol_factor_from = 1/1e6
    else:
        pass

    if toUnit[:2] == "ml":
        vol_factor_to = 1/1000
    elif toUnit[:2] == "nl":
        vol_factor_to = 1000
    elif toUnit[:2] == "pl":
        vol_factor_to = 1e6
    else:
        pass

    return val * time_factor_from * time_factor_to * vol_factor_from * vol_factor_to

def convert_str_units(abbr):
    """ Convert string units from serial units m, u, p and s, m, h to full strings.
    :param abbr: abbreviated unit
    :type abbr: str
    :return: str
    """
    first_part = abbr[0] + "l"
    if abbr[2] == "s":
        second_part = "sec"
    elif abbr[2] == "m":
        second_part = "min"
    elif abbr[2] == "h":
        second_part = "hor" # is that true?
    else:
        raise ValueError("Unknown unit")
    
    resp = first_part + "/" + second_part
    return resp

class Chain(serial.Serial):
    """Create Chain object.
    Harvard syringe pumps are daisy chained together in a 'pump chain'
    off a single serial port. A pump address is set on each pump. You
    must first create a chain to which you then add Pump objects.
    Chain is a subclass of serial.Serial. Chain creates a serial.Serial
    instance with the required parameters, flushes input and output
    buffers (found during testing that this fixes a lot of problems) and
    logs creation of the Chain. Adapted from pumpy on github.
    """
    def __init__(self, port:str, baudrate:int=9600, timeout:float=0.1):
        """
        :param port: Port of pump at PC
        :type port: str
        """
        serial.Serial.__init__(self, port=port, stopbits=serial.STOPBITS_TWO, parity=serial.PARITY_NONE, bytesize=serial.EIGHTBITS, xonxoff= False, baudrate = baudrate, timeout=timeout)
        self.flushOutput()
        self.flushInput()
        logging.info('Chain created on %s',port)
        
    def __repr__(self):
        """Return string representation of Chain object."""
        return f"Pump chain on {self.port}"
    
    def __enter__(self):
        #this is called by doing the with... construction
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        #Exception handling here, if an error occurs in the with... block
        self.close()

class Pump:
    """Create Pump object for Harvard Pump.
    Argument:
        Chain: pump chain
    Optional arguments:
        address: pump address. Default is 0.
        name: used in logging. Default is Ultra.
    """
    def __init__(self, chain, address=0, name='Ultra'):
        self.name = name
        self.serialcon = chain
        self.address = '{0:02.0f}'.format(address)
        self.diameter = None
        self.flowrate = None
        self.targetvolume = None
        self.state = None

        """Query model and version number of firmware to check pump is
        OK. Responds with a load of stuff, but the last three characters
        are XXY, where XX is the address and Y is pump status. :, > or <
        when stopped, running forwards, or running backwards. Confirm
        that the address is correct. This acts as a check to see that
        the pump is connected and working."""
        try:
            self.write('ver')
            resp = self.read(17)

            if int(resp[0:2]) != int(self.address):
                raise PumpError('No response from pump at address %s' %
                                self.address)
            
            if resp[2] == ':':
                self.state = 'idle'
            elif resp[2] == '>':
                self.state = 'infusing'
            elif resp[2] == '<':
                self.state = 'withdrawing'
            else:
                raise PumpError('%s: Unknown state encountered' % self.name)

        except PumpError:
            self.serialcon.close()
            raise

        logging.info('%s: created at address %s on %s', self.name,
                      self.address, self.serialcon.port)

    def __repr__(self):
        string = ''
        for attr in self.__dict__:
            string += '%s: %s\n' % (attr,self.__dict__[attr]) 
        return string

    def write(self, command):
        """ Write serial command to pump. 
        :param command: command to write
        :type command: str
        """
        self.serialcon.write((self.address + command + '\r').encode())

    def read(self, bytes=5):
        """ Read serial stream from pump. 
        The response is in the format: "XX:REPLY" where XX is the address, : is the state (<,>,:, or *) and REPLY is the reply from the command you gave.
        :param bytes: number of bytes to read
        :type bytes: int
        :return: str
        """
        response = self.serialcon.read(bytes)

        if len(response) == 0:
            pass
            # raise PumpError('%s: no response to command' % self.name)
        else:
            response = response.decode()
            response = response.replace('\n', '')
            return response

    def setdiameter(self, diameter):
        """Set syringe diameter (millimetres).
        Pump syringe diameter range is 0.1-35 mm. Note that the pump
        ignores precision greater than 2 decimal places. If more d.p.
        are specificed the diameter will be truncated.
        :param diameter: syringe diameter
        :type diameter: float
        """
        if self.state == 'idle':
            if diameter > 35 or diameter < 0.1:
                raise PumpError('%s: diameter %s mm is out of range' % 
                                (self.name, diameter))

            str_diameter = "%2.2f" % diameter

            # Send command   
            self.write('diameter ' + str_diameter)
            resp = self.read(80).splitlines()
            last_line = resp[-1]

            # Pump replies with address and status (:, < or >)        
            if (last_line[2] == ':' or last_line[2] == '<' or last_line[2] == '>'):
                # check if diameter has been set correctlry
                self.write('diameter')
                resp = self.read(45)
                returned_diameter = remove_crud(resp[3:9])
                
                # Check diameter was set accurately
                if float(returned_diameter) != diameter:
                    logging.error('%s: set diameter (%s mm) does not match diameter'
                                ' returned by pump (%s mm)', self.name, diameter,
                                returned_diameter)
                elif float(returned_diameter) == diameter:
                    self.diameter = float(returned_diameter)
                    logging.info('%s: diameter set to %s mm', self.name,
                                self.diameter)
            else:
                raise PumpError('%s: unknown response to setdiameter' % self.name)
        else:
            print("Please wait until pump is idle.\n")

    def setwithdrawrate(self, flowrate, unit):
        """Set withdraw rate.
        The pump will tell you if the specified flow rate is out of
        range. This depends on the syringe diameter. See Pump manual.
        :param flowrate: withdrawing flowrate
        :type flowrate: float
        :param unit: unit of flowrate. can be [m,u,p]/[h,m,s]
        :type unit: str 
        """
        if self.state == 'idle':
            self.write('wrate ' + str(flowrate) + ' ' + unit)
            resp = self.read(7)
            
            if (resp[2] == ':' or resp[2] == '<' or resp[2] == '>'):
                # Flow rate was sent, check it was set correctly
                self.write('wrate')
                resp = self.read(150).splitlines()[0]

                if 'Argument error' in resp:
                    raise PumpError('%s: flow rate (%s %s) is out of range' %
                            (self.name, flowrate, unit))

                idx1 = resp.find(str(flowrate)[0])
                idx2 = resp.find("l/")
                returned_flowrate = remove_crud(resp[idx1:idx2-1])
                returned_unit = resp[idx2-1:idx2+5]
                returned_flowrate = convert_units(float(returned_flowrate), returned_unit, convert_str_units(unit))

                if returned_flowrate != flowrate:
                    logging.error('%s: set flowrate (%s %s) does not match'
                                'flowrate returned by pump (%s %s)',
                                self.name, flowrate, unit, returned_flowrate, unit)
                elif returned_flowrate == flowrate:
                    self.flowrate = returned_flowrate
                    logging.info('%s: flow rate set to %s uL/min', self.name,
                                self.flowrate)
            else:
                raise PumpError('%s: unknown response' % self.name)
        else:
            print("Please wait until pump is idle.\n")

    def setinfusionrate(self, flowrate, unit):
        """Set infusion rate.
        The pump will tell you if the specified flow rate is out of
        range. This depends on the syringe diameter. See Pump manual.
        :param flowrate: withdrawing flowrate
        :type flowrate: float
        :param unit: unit of flowrate. can be [m,u,p]/[h,m,s]
        :type unit: str 
        """
        if self.state == "idle":
            self.write('irate ' + str(flowrate) + ' ' + unit)
            resp = self.read(17)
            
            if (":" in resp or "<" in resp or ">" in resp):
                # Flow rate was sent, check it was set correctly
                self.write('irate')
                resp = self.read(150)

                if 'error' in resp:
                    raise PumpError('%s: flow rate (%s %sl) is out of range' %
                            (self.name, flowrate, unit))

                matches = re.search(r"(\d+\.?\d*) ([mup][l])", resp)
                if matches is None:
                    raise PumpError("Syringe volume could not be found")
                else:
                    returned_flowrate = matches.group(1)
                    returned_unit = matches.group(2)

                returned_flowrate = convert_units(float(returned_flowrate), returned_unit, convert_str_units(unit))

                if returned_flowrate != flowrate:
                    logging.error('%s: set flowrate (%s %s) does not match'
                                'flowrate returned by pump (%s %s)',
                                self.name, flowrate, unit, returned_flowrate, unit)
                elif returned_flowrate == flowrate:
                    self.flowrate = returned_flowrate
                    logging.info('%s: flow rate set to %s uL/min', self.name,
                                self.flowrate)
            else:
                raise PumpError('%s: unknown response' % self.name)
        else:
            print("Please wait until pump is idle.\n")

    def infuse(self):
        """Start infusing pump."""
        if self.state == 'idle':
            self.write('irun')
            resp = self.read(55)

            if "Command error" in resp:
                error_msg = resp.splitlines()[1]
                raise PumpError('%s: %s', (self.name, error_msg))
            
            # pump doesn't respond to serial commands while infusing
            self.state = "infusing"
            threading.Thread(target=self.waituntilfinished)            
        else:
            print("Please wait until the pump is idle before infusing.\n")

    def waituntilfinished(self):
        """ Try to read pump state and return it. """
        while self.state == "infusing" or self.state == "withdrawing":
            try:
                resp = self.read(5)
                if 'T*' in resp:
                    self.state = "idle"
                    return "finished"
            except:
                pass
        
    def withdraw(self):
        """Start withdrawing pump."""
        if self.state == 'idle':
            self.write('wrun')
            resp = self.read(85)

            if "Command error" in resp:
                error_msg = resp.splitlines()[1]
                raise PumpError('%s: %s', (self.name, error_msg))
            
            # pump doesn't respond to serial commands while withdrawing
            self.state = "withdrawing"
            threading.Thread(target=self.waituntilfinished)
        else:
            print("Please wait until the pump is idle before withdrawing.\n")

    def settargetvolume(self, targetvolume, unit):
        """Set target volume.
        The pump will tell you if the specified target volume is out of
        range. This depends on the syringe. See Pump manual.
        :param targetvolume: target volume
        :type targetvolume: float
        :param unit: unit of targetvolume. Can be [m,u,p]
        :type unit: str 
        """
        if self.state == 'idle':
            self.write('tvolume ' + str(targetvolume) + ' ' + unit)
            resp = self.read(7)
            
            if True:
                # Target volume was sent, check it was set correctly
                self.write('tvolume')
                resp = self.read(150)

                if 'Target volume not set' in resp:
                    raise PumpError('%s: Target volume (%s %s) could not be set' %
                            (self.name, targetvolume, unit))

                matches = re.search(r"(\d+\.?\d*) ([mup][l])", resp)
                if matches is None:
                    raise PumpError("Syringe volume could not be found")
                else:
                    returned_targetvolume = matches.group(1)
                    returned_unit = matches.group(2)

                returned_targetvolume = convert_units(float(returned_targetvolume), returned_unit + "/min", convert_str_units(unit + "/min"))

                if returned_targetvolume != targetvolume:
                    logging.error('%s: set targetvolume (%s %s) does not match'
                                'targetvolume returned by pump (%s %s)',
                                self.name, targetvolume, unit, returned_targetvolume, unit)
                elif returned_targetvolume == targetvolume:
                    self.targetvolume = returned_targetvolume
                    logging.info('%s: target volume set to %s %s', self.name,
                                self.targetvolume, convert_str_units(unit + "/min")[:2])
            else:
                raise PumpError('%s: unknown response' % self.name)  
        else:
            print("Please wait until pump is idle.\n")

    def gettargetvolume(self):
        """Get target volume.
        :return: str
        """
        # Target volume was sent, check it was set correctly
        self.write('tvolume')
        resp = self.read(150)

        if 'Target volume not set' in resp:
            raise PumpError('%s: Target volume not be set' %
                        self.name)

        matches = re.search(r"(\d+\.?\d*) ([mup][l])", resp)
        if matches is None:
            raise PumpError("Target value could not be found")
        else:
            returned_targetvolume = matches.group(1)
            returned_unit = matches.group(2)
        
        rtn_str = returned_targetvolume + " " + returned_unit
        return rtn_str

    def setsyringevolume(self, vol, unit):
        """ Sets syringe volume.
        :param vol: volume of syringe
        :param unit: volume unit, can be [m, u, p]
        :type vol: float
        :type unit: str
        """
        if self.state == 'idle':
            self.write('svolume ' + str(vol) + ' ' + unit + 'l')
            resp = self.read(10)

            if (resp[-1] == ':' or resp[-1] == '<' or resp[-1] == '>'):
                # Volume was sent, check it was set correctly
                volume_str = self.getsyringevolume()
                returned_volume = volume_str[:-3]
                returned_unit = volume_str[-2:]
                returned_volume = convert_units(float(returned_volume), returned_unit + "/min", convert_str_units(unit + "/min"))

                if returned_volume != vol:
                    logging.error('%s: set syringe volume (%s %s) does not match'
                                'syringe volume returned by pump (%s %s)',
                                self.name, vol, unit, returned_volume, unit)
                elif returned_volume == vol:
                    self.syringevolume = returned_volume
                    logging.info('%s: syringe volume set to %s %s', self.name,
                                self.syringevolume, convert_str_units(unit + "/min")[:2])
            else:
                raise PumpError('%s: unknown response' % self.name) 
        else:
            print("Please wait until pump is idle.\n")  

    def getsyringevolume(self):
        """ Gets syringe volume. 
        :return: str
        """
        self.write('svolume')
        resp = self.read(60)
        
        matches = re.search(r"(\d+\.?\d*) ([mup][l])", resp)
        if matches is None:
            raise PumpError("Syringe volume could not be found")
        else:
            returned_volume = matches.group(1)
            returned_unit = matches.group(2)
        
        rtn_str = returned_volume + " " + returned_unit
        return rtn_str

    def stop(self):
        """Stop pump.
        To be used in an emergency as pump should stop if target is reached.
        """
        self.write('stop')
        resp = self.read(5)
        
        if resp[:3] != self.address + ":":
            raise PumpError('%s: unexpected response to stop' % self.name)
        else:
            logging.info('%s: stopped',self.name)
            self.state = "idle"

    def cvolume(self):
        """ Clears both withdrawn and infused volume """
        self.civolume()
        self.cwvolume()

    def civolume(self):
        """ Clears infused volume """
        self.write('civolume')
    
    def ctvolume(self):
        """ Clears target volume """
        self.write('ctvolume')

    def cwvolume(self):
        """" Clears withdrawn volume """
        self.write('cwvolume')

    def ivolume(self):
        """ Displays infused volume
        :return: str
        """
        self.write('ivolume')
        resp = self.read(55)

        matches = re.search(r"(\d+\.?\d*) ([mup][l])", resp)
        if matches is not None:
            return matches.group(1) + " " + matches.group(2)
        else:
            raise PumpError('%s: Unknown answer received' % self.name)

    def wvolume(self):
        """ Displays withdrawn volume
        :return: str
        """
        self.write('wvolume')
        resp = self.read(55)

        matches = re.search(r"(\d+\.?\d*) ([mup][l])", resp)
        if matches is not None:
            return matches.group(1) + " " + matches.group(2)
        else:
            raise PumpError('%s: Unknown answer received' % self.name)

class Pump2000(Pump):
    """ Create pump object for Harvard PhD 2000 pump. """

    def __init__(self, chain, address=00, name='PhD2000'):
        self.name = name
        self.serialcon = chain
        self.address = '{0:02.0f}'.format(address)
        self.diameter = None
        self.flowrate = None
        self.targetvolume = None
        self.state = None

        """Query model and version number of firmware to check pump is
        OK. Responds with a load of stuff, but the last three characters
        are XXY, where XX is the address and Y is pump status. :, > or <
        when stopped, running forwards, or running backwards. Confirm
        that the address is correct. This acts as a check to see that
        the pump is connected and working."""
        try:
            self.write('VER')
            resp = self.read(17)

            if 'PHD' not in resp:
                raise PumpError('No response from pump at address %s' %
                                self.address)
            
            if resp[-1] == ':':
                self.state = 'idle'
            elif resp[-1] == '>':
                self.state = 'infusing'
            elif resp[-1] == '<':
                self.state = 'withdrawing'
            elif resp[-1] == '*':
                self.state = 'stalled'
            else:
                raise PumpError('%s: Unknown state encountered' % self.name)

        except PumpError:
            self.serialcon.close()
            raise

        logging.info('%s: created at address %s on %s', self.name,
                      self.address, self.serialcon.port)

    def waituntilfinished(self):
        """ Try to read pump state and return it. """
        while self.state == "infusing" or self.state == "withdrawing":
            try:
                resp = self.read(5)
                if '*' in resp:
                    self.state = "idle"
                    return "finished"
            except:
                pass

    def run(self):
        self.write('RUN')
        resp = self.read(17)

        self._errorcheck(resp)

        self.state = 'infusing'

    def rev(self):
        self.write('REV')
        resp = self.read(17)

        self._errorcheck(resp)

        self.state = 'withdrawing'

    def infuse(self):
        self.run()
       
        if self.state == 'withdrawing':
            self.stop()
            self.rev()
    
    def withdraw(self):
        self.rev()

        if self.state == 'infusing':
            self.stop()
            self.run()

    def stop(self):
        self.write('STP')
        resp = self.read(17)

        self._errorcheck(resp)

        sleep(0.1)
        if self.state == 'infusing' or self.state == 'withdrawing':
            raise PumpError('%s: Pump could not be stopped.' % self.name)

    def _errorcheck(self, resp):
        if resp[-1] == ':':
            self.state = 'idle'
        elif resp[-1] == '>':
            self.state = 'infusing'
        elif resp[-1] == '<':
            self.state = 'withdrawing'
        elif resp[-1] == '*':
            self.state = 'stalled'
        else:
            raise PumpError('%s: Unknown state encountered' % self.name)

    def clear_accumulated_volume(self):
        self.write('CLV')
        resp = self.read(17)

        self._errorcheck(resp)

    def clear_target_volume(self):
        self.write('CLT')
        resp = self.read(17)

        self._errorcheck(resp)

    def set_rate(self, flowrate, units):
        flowrate_str = "%4.4f" %flowrate
        if units == 'm/m':
            write_str = 'MLM'
        elif units == 'u/m':
            write_str = 'ULM'
        elif units == 'm/h':
            write_str = 'MLH'
            self.rate_units = "ml/h"
        elif units == 'u/h':
            write_str = 'ULH'
        else:
            raise PumpError('%s: Unknown unit specified' % self.name)

        self.write(write_str + flowrate_str)
        resp = self.read(17)
        self._errorcheck(resp)

    def setdiameter(self, diameter):
        self.write('MMD' + str(diameter))
        resp = self.read(17)
        self._errorcheck(resp)

    def settargetvolume(self, volume):
        """ Set target volume in mL. """
        self.write('MLT' + str(volume))
        resp = self.read(17)
        self._errorcheck(resp)

    def getdiameter(self):
        self.write('DIA')
        resp = self.read(17)

        self._errorcheck(resp)
        matches = re.search(r"(\d+\.?\d*)", resp)
        if matches is not None:
            return matches.group(1) + " mm"
        else:
            raise PumpError('%s: Unknown answer received' % self.name)

    def getrate(self):
        self.write('RAT')
        resp = self.read(19)

        self._errorcheck(resp)
        matches = re.search(r"(\d+\.?\d*)", resp)
        if matches is not None:
            self.write('RNG')
            resp = self.read(17)
            self._errorcheck(resp)
            return matches.group(1) + " " + resp[:4]
        else:
            raise PumpError('%s: Unknown answer received' % self.name)
        
    def ivolume(self):
        self.write('VOL')
        resp = self.read(17)

        self._errorcheck(resp)
        matches = re.search(r"(\d+\.?\d*)", resp)
        if matches is not None:
            return matches.group(1) + " " + "ml"
        else:
            raise PumpError('%s: Unknown answer received' % self.name)
    
    def gettargetvolume(self):
        self.write('TAR')
        resp = self.read(17)

        self._errorcheck(resp)
        matches = re.search(r"(\d+\.?\d*)", resp)
        if matches is not None:
            return matches.group(1) + " " + "ml"
        else:
            raise PumpError('%s: Unknown answer received' % self.name)

class PumpModel33:
    """Create Pump object for Harvard Model 33 twin syringe pump.

    Parameters
    ----------
    chain : Chain
        Pump chain.
    address : int, optional
        Pump address. Default is 0.
    name : str, optional
        Used in logging. Default is Model33.
    """
    def __init__(self, chain, address=0, name='Model33'):
        self.name = name
        self.serialcon = chain
        self.address = '{0:02.0f}'.format(address)
        self.state = None
        self.mode = None
        self.direction = None
        self.parallel_reciprocal = None
        self.syringe_selection = {
            0 : "",
            1 : "A",
            2 : "B",
        }
        self.unit_conversion = {
            "ul/mn": "UM",
            "ml/mn": "MM",
            "ul/hr": "UH",
            "ml/hr": "MH",
        }
        # Update state and check firmware version. This acts as a check to see that the pump is connected and working.
        try:
            self.firmware_version = self.get_version()
            if not self.firmware_version.startswith('33'):
                logging.warning(f'{self.name}: firmware version {self.firmware_version} indicates this is probably not a Model 33 pump. Continue at your own risk.')
            self.update_state()
        except PumpError:
            self.serialcon.close()
            raise
        logging.info(f'{self.name}: created at address {self.address} on {self.serialcon.port}')

    def __repr__(self):
        self.update_state()
        rep = f"PumpModel33 Object (name = {self.name}) on <{str(self.serialcon)}> with address <{self.address}>.\n"
        rep += f"State: {self.state}, Mode: {self.mode}, Direction: {self.direction}, Parallel/Reciprocal: {self.parallel_reciprocal}"
        return rep

    def write(self, command: str):
        """Write serial command to pump.

        Parameters
        ----------
        command : str
            Command to write.
        """
        logging.debug(f'{self.name}: writing command: {command}')
        self.serialcon.write((command + '\r').encode())

    def read(self, bytes:int=80) -> str:
        """Read serial stream from pump.

        Parameters
        ----------
        bytes : int, optional
            Number of bytes to read (default is 80).

        Returns
        -------
        str
            Response string from the pump.
        """
        response = self.serialcon.read(bytes)
        logging.debug(f'{self.name}: reading response: {response}')
        if len(response) == 0:
            logging.warning(f'{self.name}: no response to command')
            return ''
        else:
            response = response.decode()
            return response 

    def issue_command(self, command: str, value:str = '', syringe: int = 0, units: str = "") -> list[str]:
        """
        Write serial command to pump, and listen to response.

        Parameters
        ----------
        command : str
            Command to write.
        value : str, optional
            Value to write with the command (default is an empty string).
        syringe : int, optional
            Syringe number to act on (default is 0).
        units : str, optional
            Units for the value (default is an empty string).

        Returns
        -------
        list of str
            List of response lines from the pump. Typically, you only care about the last line.
        """
        syringe_command = self.syringe_selection[syringe]
        instruction =  (self.address + command + syringe_command + value + units).strip()
        self.write(instruction)
        response = self.read(80).splitlines()
        if not response or len(response) == 0:
            raise PumpError(f'{self.name}: no response to command <{instruction}> - pump may be disconnected?')
        # The next lines handle the error response from the pump.
        elif '?' in response[1]:
            logging.error(f'{self.name}: pump reported SYNTAX ERROR when <{instruction}> was issued.')
            raise PumpSyntaxError(f'{self.name}: pump reported SYNTAX ERROR when <{instruction}> was issued.')
        elif 'NA' in response[1]:
            logging.error(f'{self.name}: pump reported COMMAND NOT APPLICABLE AT THIS TIME error when <{instruction}> was issued.')
            raise PumpNotApplicableError(f'{self.name}: pump reported COMMAND NOT APPLICABLE AT THIS TIME error when <{instruction}> was issued.')
        elif 'OOR' in response[1]:
            logging.error(f'{self.name}: pump reported OUT OF RANGE error when <{instruction}> was issued.')
            raise PumpOutOfRangeError(f'{self.name}: pump reported OUT OF RANGE error when <{instruction}> was issued.')
        logging.debug(f'{self.name}: response passed to handler function: {response}')
        return response

    def parse_float_response(self, response: str) -> float:
        """
        Parse a float value from a response string.

        Parameters
        ----------
        response : str
            Response string from the pump.

        Returns
        -------
        float
            Parsed float value.
        """
        try:
            return float(response.strip())
        except ValueError:
            raise PumpError(f'{self.name}: could not parse float from response {response}')

    def parse_float_to_str(self, number: float) -> str:
        """
        Convert a float to a string with 5 symbols, including the seperator.
        e.g. 12.3 becomes 12.30, 12.345 becomes 12.35, and 2.1 becomes 2.100.

        Parameters
        ----------
        number : float
            Number to convert.

        Returns
        -------
        str
            String representation of the number with two decimal places.
        """
        if not (0 <= number < 9999):
            raise ValueError(f'{self.name}: {number} is out of range for parsing, must be between 0 and 9999')
        parsed = f"{number:.3f}"[:5].ljust(5, '0')
        return parsed

    def run(self, already_running_ok: bool = True):
        """
        Starts the pump. If the pump is already running and `already_running_ok` is False, the method raises an exception.
        Parameters
        ----------
        already_running_ok : bool, optional
            If True, does not raise an error if the pump is already running (default is True).
        """
        try:
            resp = self.issue_command('RUN')
        except PumpNotApplicableError as e:
            if already_running_ok:
                logging.info(f'{self.name}: Pump is already running, continuing without error.')
                return
            else:
                raise PumpNotApplicableError(f'{self.name}: Pump is already running, cannot start pump.')
        state = self.get_state()

        if (state == '<' or state == '>'):
            self.state = 'infusing'
            logging.info(f'{self.name}: Pump has started running')
        else:
            raise PumpError(f'{self.name}: pump is not running: {state}')
        self.update_state()

    def stop(self, already_stopped_ok: bool = True):
        """
        Stops pump. If the pump is already stopped, nothing will happen.
        """
        try:
            resp = self.issue_command('STP')
        except PumpNotApplicableError as e:
            if already_stopped_ok:
                logging.info(f'{self.name}: Pump is already stopped, continuing without error.')
            else:
                raise PumpNotApplicableError(f'{self.name}: Pump is already stopped, cannot stop pump.')
       
        state = self.get_state()
        if (state == ':'):
            self.state = 'idle'
            logging.info(f'{self.name}: stopped pump')
        else:
            raise PumpError(f'{self.name}: pump has not stopped: {state}')
        self.update_state()

    def update_state(self):
        """Update the state of the pump."""
        self.state = self.get_state()
        self.mode = self.get_mode()
        self.direction = self.get_direction()
        self.parallel_reciprocal = self.get_parallel_reciprocal()
        if self.state == '*':
            logging.warning(f'{self.name}: pump is stalled, please check the syringe!')

    def log_all_parameters(self):
        """Log all parameters of the pump."""
        self.update_state()
        logging.info(f'{self.name}: logging all parameters:')
        logging.info(f'{self.name}: firmware version: {self.firmware_version}')
        logging.info(f'{self.name}: state: {self.state}, mode: {self.mode}, direction: {self.direction}, parallel/reciprocal: {self.parallel_reciprocal}')
        d1, d2 = self.get_diameter(syringe=1), self.get_diameter(syringe=2)
        r1, r2 = self.get_rate(syringe=1), self.get_rate(syringe=2)
        logging.info(f'{self.name}: syringe 1 diameter: {d1} mm, flowrate: {r1}')
        logging.info(f'{self.name}: syringe 2 diameter: {d2} mm, flowrate: {r2}')
        
    def get_mode(self) -> str:
        """Get the current mode of the pump.

        Returns
        -------
        str
            Can be AUT(o stop), PRO(portional), or CON(tinuous).
        """
        resp = self.issue_command('MOD')
        return resp[1]
    
    def get_state(self) -> str:
        """Get the current state of syringe 1 of the pump.

        Returns
        -------
        str
            idle (:), infusing (>), withdrawing (<), or stalled (*).
            Syringe 2 state depends on parallel/reciprocal setting, see self.get_parallel_reciprocal.
        """
        response = self.issue_command('MOD')
        return response[2][1]

    def get_direction(self) -> str:
        """Get the current direction of syringe 1 of the pump.

        Returns
        -------
        str
            Can be INFUSE (outward flow) or REFILL (inward flow).
            Syringe 2 direction depends on parallel/reciprocal setting, see self.get_parallel_reciprocal.
        """
        response = self.issue_command('DIR')
        return response[1]
    
    def get_parallel_reciprocal(self) -> str:
        """Get the current parallel/reciprocal setting of the pump.

        Returns
        -------
        str
            Can be ON (parallel) or OFF (Reciprocal).
        """
        response = self.issue_command('PAR')
        return response[1]

    def set_mode(self, mode: str):
        """Set the mode of the pump.

        Parameters
        ----------
        mode : str
            Mode to set, can be AUT(o stop), PRO(portional), or CON(tinuous).
        """
        if mode not in ['AUT', 'PRO', 'CON']:
            raise PumpError(f'{self.name}: unknown mode {mode}')
        
        resp = self.issue_command('MOD', mode)
        set_mode = self.get_mode()

        if (set_mode == mode):
            logging.info(f'{self.name}: mode set to {mode}')
        else:
            raise PumpError(f'{self.name}: mode not set correctly, response to set_mode {mode}: {set_mode}')
        self.update_state()

    def set_direction(self, direction: str):
        """Set the direction of the pump.

        Parameters
        ----------
        direction : str
            Direction to set, can be INF(use), REF(ill), or REV(erse).
        """
        if direction not in ['INF', 'REF', 'REV']:
            raise PumpError(f'{self.name}: unknown direction {direction}')
        
        old_direction = self.get_direction()
        resp = self.issue_command('DIR', direction)
        new_direction = self.get_direction()

        if direction in ['INF','REV'] and (new_direction[:3] == direction):
            logging.info(f'{self.name}: direction set to {direction}')
        elif direction == 'REF' and (new_direction != old_direction) and (new_direction[:3] in ['INF','REV']):
            logging.info(f'{self.name}: direction reversed to {direction}')
        else:
            raise PumpError(f'{self.name}: direction not set correctly, response to set_direction {direction}: {new_direction}')
        self.update_state()

    def set_parallel_reciprocal(self, setting: str):
        """Set the parallel/reciprocal setting of the pump.

        Parameters
        ----------
        setting : str
            Setting to set, can be ON (parallel) or OFF (Reciprocal).
        """
        if setting not in ['ON', 'OFF']:
            raise PumpError(f'{self.name}: unknown parallel/reciprocal setting {setting}')
        
        resp = self.issue_command('PAR', setting)
        parrep = self.get_parallel_reciprocal()
        if (parrep == setting):
            logging.info(f'{self.name}: parallel/reciprocal set to {setting}')
        else:
            raise PumpError(f'{self.name}: parallel/reciprocal not set correctly, response to set_parallel_reciprocal {setting}: {last_line}')
        self.update_state()
        
    def set_diameter(self, diameter : float, syringe:int=0):
        """Set syringe diameter (always in millimetres).

        Parameters
        ----------
        diameter : float
            Syringe diameter.
        syringe : int, optional
            Syringe number to set diameter for, 0 for do not pass on (either defaults to syringe 1 or is not used).
        """
        if not (0.1 < diameter < 50): # manual gives these limits
            raise PumpError(f'{self.name}: diameter {diameter} mm is out of range')
        elif syringe > 1 and self.get_mode() != "PRO":
            raise PumpError(f'{self.name}: can only set diameter for syringe <{syringe}> if pump is in PRO(portional) mode')
        elif self.get_state() in ("<", ">", "*"):
            raise PumpError(f'{self.name}: cannot set diameter while pump is running, please stop the pump first')
               
        str_diameter = self.parse_float_to_str(diameter)
        resp = self.issue_command('DIA', str_diameter, syringe) 
        returned_diameter = self.get_diameter(syringe)
        # Check diameter was set accurately
        if ("%2.2f" % returned_diameter) != str_diameter:
            logging.error(f'{self.name}: set diameter ({diameter} mm) does not match diameter returned by pump ({returned_diameter} mm)')
        elif float(returned_diameter) == diameter:
            logging.info(f'{self.name}: diameter set to {diameter} mm')
        self.update_state()

    def get_diameter(self, syringe:int=0) -> float:
        """Get syringe diameter.

        Parameters
        ----------
        syringe : int, optional
            Syringe number to get diameter for, 0 for do not pass on (either defaults to syringe 1 or is not used).

        Returns
        -------
        float
            Syringe diameter in mm.
        """
        resp = self.issue_command('DIA', syringe = syringe)
        relevant_line = resp[1]
        returned_diameter = self.parse_float_response(relevant_line)
        logging.debug(f'{self.name}: diameter of syringe <{syringe}> is {returned_diameter} mm')
        return returned_diameter

    def set_rate(self, flowrate:float, unit:str="ml/hr", syringe:int=0):
        """
        Set flow rate.

        Parameters
        ----------
        flowrate : float
            Flow rate to set.
        unit : str, optional
            Unit of flow rate, can be 'ml/hr', 'ul/hr', 'ml/mn', or 'ul/mn' (default is 'ml/hr').
        syringe : int, optional
            Syringe number to set rate for, 0 for do not pass on (either defaults to syringe 1 or is not used) (default is 0).
        """
        if unit not in self.unit_conversion:
            raise ValueError(f'{self.name}: unknown unit {unit}, must be one of {list(self.unit_conversion.keys())}')
        actual_units = self.unit_conversion[unit]
        parsed_flowrate = self.parse_float_to_str(flowrate)
        resp = self.issue_command('RAT', f"{parsed_flowrate}", syringe, actual_units)
        rate_reply = self.get_rate(syringe)
        
        logging.debug(f'{self.name}: flowrate of syringe <{syringe}> set to {float(parsed_flowrate)}, outcome = {rate_reply[0]}')
        logging.debug(f'{self.name}: unit of syringe <{syringe}> set to {unit}, outcome = {rate_reply[1]}')

        if (float(parsed_flowrate) == rate_reply[0]) and (unit == rate_reply[1]):
            logging.info(f'{self.name}: flowrate of syringe <{syringe}> set to {flowrate} {unit}')
        else:
            raise PumpError(f'{self.name}: flowrate of syringe <{syringe}> not set correctly, response to set_rate {flowrate} {unit}: {rate_reply}')
        self.update_state()
        
    def get_rate(self, syringe:int=0) -> tuple[float, str]:
        """Get flow rate.

        Parameters
        ----------
        syringe : int, optional
            Syringe number to get rate for, 0 for do not pass on (either defaults to syringe 1 or is not used).

        Returns
        -------
        tuple of float and str
            Flow rate and its units.
        """
        resp = self.issue_command('RAT', syringe=syringe)
        relevant_line = resp[1]
        number = relevant_line[0:6]
        unit = relevant_line[6:].strip()
        returned_flowrate = self.parse_float_response(number)
        logging.debug(f'{self.name}: flow rate is {returned_flowrate} {unit}')
        return (returned_flowrate, unit)

    def get_version(self) -> str:
        """Get the version of the pump firmware.

        Returns
        -------
        str
            Version string of the pump.
        """
        resp = self.issue_command('VER')
        version = resp[1].strip()
        logging.debug(f'{self.name}: firmware version is {version}')
        return version

    def sleep_with_heartbeat(self, seconds: float, beat_interval: float = 1, error_wakeup: bool = False):
        """Sleep for a specified number of seconds, while checking the pump state to watch for stall, and making sure pump is not disconnected during wait.

        Parameters
        ----------
        seconds : float
            Number of seconds to sleep.
        beat_interval : float, optional
            Interval in seconds to check the pump state (default is 1 second).
        error_wakeup : bool, optional
            If True, will raise a PumpError if the pump state changes to stalled or disconnected during the sleep period (default is False).
        """
        end_time = time.time() + seconds
        while time.time() < end_time:
            self.update_state()
            if self.state == '*' and error_wakeup:
                raise PumpError(f'{self.name}: pump has stalled, please check the syringe(s)!')
            time.sleep(beat_interval)

class PumpError(Exception):
    pass

class PumpSyntaxError(PumpError):
    """Raised when the pump returns a syntax error."""
    def __init__(self, message):
        super().__init__(message)

class PumpOutOfRangeError(PumpError):
    """Raised when the pump returns an out of range error."""
    def __init__(self, message):
        super().__init__(message)

class PumpNotApplicableError(PumpError):
    """Raised when the pump returns a command not applicable error."""
    def __init__(self, message):
        super().__init__(message)
    