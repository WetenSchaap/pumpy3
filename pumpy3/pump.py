import serial
import logging
import time
from time import sleep

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
    """Base class for Pump objects."""
    def __init__(self, chain: Chain, address: int = 0, name: str = 'Pump'):
        self.name = name
        self.serialcon = chain
        self.address = '{0:02.0f}'.format(address)
        self.state = None
        self.mode = None
        self.direction = None
        self.parallel_reciprocal = None
        self.unit_conversion = {
            "ul/mn": "UM",
            "ml/mn": "MM",
            "ul/hr": "UH",
            "ml/hr": "MH",
        }
        try:
            self.firmware_version = self.get_version()
            self.update_state()
        except PumpError:
            self.serialcon.close()
            raise
        logging.info(f'{self.name}: created at address {self.address} on {self.serialcon.port}')

    def __repr__(self):
        self.update_state()
        rep = f"{self.__class__.__name__} Object (name = {self.name}) on <{str(self.serialcon)}> with address <{self.address}>.\n"
        rep += f"State: {self.state}, Mode: {self.mode}, Direction: {self.direction}, Parallel/Reciprocal: {self.parallel_reciprocal}"
        return rep

    def write(self, command: str):
        logging.debug(f'{self.name}: writing command: {command}')
        self.serialcon.write((command + '\r').encode())

    def read(self, bytes: int = 80) -> str:
        response = self.serialcon.read(bytes)
        logging.debug(f'{self.name}: reading response: {response}')
        if len(response) == 0:
            logging.warning(f'{self.name}: no response to command')
            return ''
        else:
            return response.decode()

    def issue_command(self, command: str, value: str = '', units: str = '') -> list[str]:
        instruction = (self.address + command + value + units).strip()
        self.write(instruction)
        response = self.read(80).splitlines()
        if not response or len(response) == 0:
            raise PumpError(f'{self.name}: no response to command <{instruction}> - pump may be disconnected?')
        elif '?' in response[1]:
            raise PumpSyntaxError(f'{self.name}: pump reported SYNTAX ERROR when <{instruction}> was issued.')
        elif 'NA' in response[1]:
            raise PumpNotApplicableError(f'{self.name}: pump reported COMMAND NOT APPLICABLE AT THIS TIME error when <{instruction}> was issued.')
        elif 'OOR' in response[1]:
            raise PumpOutOfRangeError(f'{self.name}: pump reported OUT OF RANGE error when <{instruction}> was issued.')
        return response

    def update_state(self):
        self.state = self.get_state()
        self.mode = self.get_mode()
        self.direction = self.get_direction()
        self.parallel_reciprocal = self.get_parallel_reciprocal()
        if self.state == '*':
            logging.warning(f'{self.name}: pump is stalled, please check the syringe!')

    def get_version(self) -> str:
        version = self.issue_command('VER')[1].strip()
        logging.debug(f'{self.name}: firmware version is {version}')
        return version

    def get_state(self) -> str:
        raise NotImplementedError("This method should be overridden in subclasses.")

    def get_mode(self) -> str:
        raise NotImplementedError("This method should be overridden in subclasses.")

    def get_direction(self) -> str:
        raise NotImplementedError("This method should be overridden in subclasses.")

    def set_direction(self, direction: str):
        raise NotImplementedError("This method should be overridden in subclasses.")

    def log_all_parameters(self):
        self.update_state()
        logging.info(f'{self.name}: logging all parameters:')
        logging.info(f'{self.name}: firmware version: {self.firmware_version}')
        logging.info(f'{self.name}: state: {self.state}, mode: {self.mode}, direction: {self.direction}, parallel/reciprocal: {self.parallel_reciprocal}')

class PumpPHD2000:
    def __init__(self, chain:Chain, address:int=0, name:str="PHD2000"):
        """
        Create Pump object for Harvard PHD 2000 twin syringe pump.

        Parameters
        ----------
        chain : Chain
            Pump chain.
        address : int, optional
            Pump address. Default is 0.
        name : str, optional
            Used in logging. Default is PHD2000.
        
        Notes
        ---------
        Commands that make use of the program function (e.g. SEQ, PGR) are intentionally not implemented - they have limited added value if you are using this script anyway.
        """
        self.name = name
        self.serialcon = chain
        self.address = '{0:02.0f}'.format(address)
        self.state = None
        self.mode = None
        self.autofill = None
        self.direction = None
        self.unit_conversion = {
            "ul/mn": "UM",
            "ml/mn": "MM",
            "ul/hr": "UH",
            "ml/hr": "MH",
        }
        self.mode_conversion = {
            "PUMP": "PMP",
            "VOLUME": "VLM",
        }
        # Update state and check firmware version. This acts as a check to see that the pump is connected and working.
        try:
            self.firmware_version = self.get_version()
            if not self.firmware_version.startswith('PHD'):
                logging.warning(f'{self.name}: firmware version {self.firmware_version} indicates this is probably not a PHD 2000 pump. Continue at your own risk.')
            self.update_state()
        except PumpError:
            self.serialcon.close()
            raise
        logging.info(f'{self.name}: created at address {self.address} on {self.serialcon.port}')

    def __repr__(self):
        self.update_state()
        rep = f"PumpPHD2000 Object (name = {self.name}) on <{str(self.serialcon)}> with address <{self.address}>.\n"
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

    def issue_command(self, command: str, value:str = '', units: str = "") -> list[str]:
        """
        Write serial command to pump, and listen to response.

        Parameters
        ----------
        command : str
            Command to write.
        value : str, optional
            Value to write with the command (default is an empty string).
        units : str, optional
            Units for the value (default is an empty string).

        Returns
        -------
        list of str
            List of response lines from the pump. Typically, you only care about the last line.
        """
        instruction =  (self.address + command + value + units).strip()
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

    def get_volume_delivered(self) -> float:
        """
        Get the volume delivered, in mL.

        Returns
        -------
        float
            Volume delivered in mL
        """
        resp = self.issue_command('DEL')
        relevant_line = resp[1]
        vol = relevant_line.strip()
        returned_volume = self.parse_float_response(vol)
        logging.debug(f'{self.name}: delivered volume is {returned_volume} mL')
        return returned_volume

    def reset_volume_delivered(self):
        """
        Reset the volume delivered to zero. Only run this when pump is not running.
        """
        if self.get_state != "~":
            raise PumpNotApplicableError(f"{self.name}:Volume delivereed can only be reset when pump is not running")
        resp = self.issue_command('CLD')
        vol_del = self.get_volume_delivered()
        if vol_del != 0:
            raise PumpError(f'{self.name}: volume delivered not succesfully reset')
        else:
            logging.info(f'{self.name}: volume delivered reset to 0 mL')
        self.update_state()

    def update_state(self):
        """Update the state of the pump."""
        self.state = self.get_state()
        self.mode = self.get_mode()
        self.direction = self.get_direction()
        if self.state == '*':
            logging.warning(f'{self.name}: pump is stalled, please check the syringe!')

    def log_all_parameters(self):
        """Log all parameters of the pump."""
        self.update_state()
        logging.info(f'{self.name}: logging all parameters:')
        logging.info(f'{self.name}: firmware version: {self.firmware_version}')
        logging.info(f'{self.name}: state: {self.state}, mode: {self.mode}, direction: {self.direction}' )
        d1 = self.get_diameter()
        r1 = self.get_rate()
        v1 = self.get_target_volume()
        logging.info(f'{self.name}: syringe diameter: {d1} mm, flowrate: {r1}, target volume: {v1}, ')
        
    def get_mode(self) -> str:
        """Get the current mode of the pump.

        Returns
        -------
        str
            Can be PUMP (pump at fixed rate), VOLUME (inject specific volume at set rate), or PGM (program - not suported by this module).
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

    def get_direction(self):
        """
        Get the current direction of the pump.
        """
        raise NotImplementedError("This method should be overridden in subclasses.")

    def set_mode(self, mode: str):
        """Set the mode of the pump.

        Parameters
        ----------
        mode : str
            Mode to set, can be PMP (pump at fixed rate), or VOL (inject specific volume at set rate). PGM (program mode) is theoretically available, but not implemented in these scripts. Use only if you know what you are doing
        """
        if mode not in ['PMP', 'VOL', 'PGM']:
            raise PumpError(f'{self.name}: unknown mode {mode}')
        if mode == 'PGM':
            logging.warning(f"{self.name}: Pump mode set to PGM (program mode). Although this mode is theoretically available, it is not implemented in these scripts. Use only if you know what you are doing")
        
        resp = self.issue_command('MOD', mode)
        set_mode = self.get_mode()
        set_mode = self.mode_conversion[set_mode]
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
        raise NotImplementedError("This method should be overridden in subclasses.")

    def get_autofill(self) -> str:
        """
        Get the auto-fill setting.

        Returns
        -------
        str
            Auto-fill can be either 'ON' or 'OFF'.
        """
        resp = self.issue_command('AF')
        relevant_line = resp[1]
        logging.debug(f'{self.name}: Auto-fill mode is {relevant_line}')
        return relevant_line

    def set_autofill(self, autofill:str):
        """
        Set the auto-fill setting. Cannot be run if the pump is running.
        """
        raise NotImplementedError("This method should be overridden in subclasses.")

    def set_diameter(self, diameter : float):
        """Set syringe diameter (always in millimetres).

        Parameters
        ----------
        diameter : float
            Syringe diameter.
        """
        if not (0.1 < diameter < 50): # manual gives these limits
            raise PumpError(f'{self.name}: diameter {diameter} mm is out of range')
        elif self.get_state() in ("<", ">", "*"):
            raise PumpError(f'{self.name}: cannot set diameter while pump is running, please stop the pump first')
               
        str_diameter = self.parse_float_to_str(diameter)
        resp = self.issue_command('DIA', str_diameter) 
        returned_diameter = self.get_diameter()
        # Check diameter was set accurately
        if ("%2.2f" % returned_diameter) != str_diameter:
            logging.error(f'{self.name}: set diameter ({diameter} mm) does not match diameter returned by pump ({returned_diameter} mm)')
        elif float(returned_diameter) == diameter:
            logging.info(f'{self.name}: diameter set to {diameter} mm')
        self.update_state()

    def get_diameter(self) -> float:
        """Get syringe diameter.

        Returns
        -------
        float
            Syringe diameter in mm.
        """
        resp = self.issue_command('DIA')
        relevant_line = resp[1]
        returned_diameter = self.parse_float_response(relevant_line)
        logging.debug(f'{self.name}: diameter of syringe is {returned_diameter} mm')
        return returned_diameter

    def set_rate(self, flowrate:float, unit:str="ml/hr"):
        """
        Set flow rate.

        Parameters
        ----------
        flowrate : float
            Flow rate to set.
        unit : str, optional
            Unit of flow rate, can be 'ml/hr', 'ul/hr', 'ml/mn', or 'ul/mn' (default is 'ml/hr').
        """
        if unit not in self.unit_conversion:
            raise ValueError(f'{self.name}: unknown unit {unit}, must be one of {list(self.unit_conversion.keys())}')
        actual_units = self.unit_conversion[unit]
        parsed_flowrate = self.parse_float_to_str(flowrate)
        resp = self.issue_command('RAT', f"{parsed_flowrate}", actual_units)
        rate_reply = self.get_rate()
        
        logging.debug(f'{self.name}: flowrate set to {float(parsed_flowrate)}, outcome = {rate_reply[0]}')
        logging.debug(f'{self.name}: unit set to {unit}, outcome = {rate_reply[1]}')

        if (float(parsed_flowrate) == rate_reply[0]) and (unit == rate_reply[1]):
            logging.info(f'{self.name}: flowrate set to {flowrate} {unit}')
        else:
            raise PumpError(f'{self.name}: flowrate not set correctly, response to set_rate {flowrate} {unit}: {rate_reply}')
        self.update_state()
        
    def get_rate(self) -> tuple[float, str]:
        """Get flow rate.

        Returns
        -------
        tuple of float and str
            Flow rate and its units.
        """
        resp = self.issue_command('RAT')
        relevant_line = resp[1]
        number = relevant_line[0:6]
        unit = relevant_line[6:].strip()
        returned_flowrate = self.parse_float_response(number)
        logging.debug(f'{self.name}: flow rate is {returned_flowrate} {unit}')
        return (returned_flowrate, unit)

    def set_refill_rate(self, flowrate:float, unit:str):
        raise NotImplementedError("This method should be overridden in subclasses.")
    
    def get_refill_rate(self) -> tuple[float,str]:
        raise NotImplementedError("This method should be overridden in subclasses.")

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

    def get_target_volume(self) -> float:
        """
        Get target volume (as needed in 'VOL' mode).

        Returns
        -------
        float
            Target volume, in unit mL
        """
        resp = self.issue_command('TGT')
        relevant_line = resp[1]
        number = relevant_line.strip()
        returned_target_volume = self.parse_float_response(number)
        logging.debug(f'{self.name}: target volume is {returned_target_volume} mL')
        return returned_target_volume

    def set_target_volume(self, volume:float):
        """
        Set target volume (as needed in 'VOL' mode).

        Parameters
        ----------
        volume : float
            Target volume in mL.
        """
        if self.get_state() in ("<", ">", "*"):
            raise PumpError(f'{self.name}: cannot set diameter while pump is running, please stop the pump first')
        str_volume = self.parse_float_to_str(volume)
        resp = self.issue_command('TGT', str_volume) 
        returned_volume = self.get_target_volume()
        # Check diameter was set accurately
        if (self.parse_float_to_str(returned_volume)) != str_volume:
            logging.error(f'{self.name}: set target volume ({volume} mL) does not match diameter returned by pump ({returned_volume}} mL)')
        else:
            logging.info(f'{self.name}: diameter set to {volume} mL')
        self.update_state()

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

class PumpPHD2000_Refill(PumpPHD2000):
    def __init__(self, chain:Chain, address:int=0, name:str='PHD2000'):
        super().__init__(chain,address,name)
    
    def __repr__(self):
        self.update_state()
        rep = f"PumpPHD2000_Refill Object (name = {self.name}) on <{str(self.serialcon)}> with address <{self.address}>.\n"
        rep += f"State: {self.state}, Mode: {self.mode}, Direction: {self.direction}, Parallel/Reciprocal: {self.parallel_reciprocal}"
        return rep
    
    def get_direction(self) -> str:
        """Get the current direction of the pump.

        Returns
        -------
        str
            Can be INFUSE (outward flow) or REFILL (inward flow).
        """
        response = self.issue_command('DIR')
        return response[1]

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

    def set_refill_rate(self, flowrate:float, unit:str="ml/hr"):
        """
        Set refill flow rate.

        Parameters
        ----------
        flowrate : float
            Refill flow rate to set.
        unit : str, optional
            Unit of flow rate, can be 'ml/hr', 'ul/hr', 'ml/mn', or 'ul/mn' (default is 'ml/hr').
        """
        if unit not in self.unit_conversion:
            raise ValueError(f'{self.name}: unknown unit {unit}, must be one of {list(self.unit_conversion.keys())}')
        actual_units = self.unit_conversion[unit]
        parsed_flowrate = self.parse_float_to_str(flowrate)
        resp = self.issue_command('RFR', f"{parsed_flowrate}", actual_units)
        rate_reply = self.get_refill_rate()
        
        logging.debug(f'{self.name}: refill flowrate set to {float(parsed_flowrate)}, outcome = {rate_reply[0]}')
        logging.debug(f'{self.name}: refill unit set to {unit}, outcome = {rate_reply[1]}')

        if (float(parsed_flowrate) == rate_reply[0]) and (unit == rate_reply[1]):
            logging.info(f'{self.name}: refill flowrate set to {flowrate} {unit}')
        else:
            raise PumpError(f'{self.name}: refill flowrate not set correctly, response to set_rate {flowrate} {unit}: {rate_reply}')
        self.update_state()
        
    def get_refill_rate(self) -> tuple[float, str]:
        """Get refill flow rate.

        Returns
        -------
        tuple of float and str
            Flow rate and its units.
        """
        resp = self.issue_command('RFR')
        relevant_line = resp[1]
        number = relevant_line[0:6]
        unit = relevant_line[6:].strip()
        returned_flowrate = self.parse_float_response(number)
        logging.debug(f'{self.name}: refill flow rate is {returned_flowrate} {unit}')
        return (returned_flowrate, unit)

    def set_autofill(self, autofill:str):
        """
        Set the auto-fill setting. Cannot be run if the pump is running.

        Parameters
        ----------
        autofill : str
            Whether auto-fill is 'ON' or 'OFF'
        """
        if self.get_state() != "~":
            raise PumpError(f'{self.name}: cannot set auto-fill while pump is running, please stop the pump first')
        elif autofill not in ["ON", "OFF"]:
            raise ValueError(f'{self.name}: <{autofill}> is not a valid choise for auto-fill mode. Select either ON or OFF')
        resp = self.issue_command('AF', autofill)
        if self.get_autofill() == autofill:
            logging.info(f'{self.name}: Auto-fill mode is set to {autofill}')
        else:
            raise PumpError(f"{self.name}: Auto-fill mode was not set to {autofill}, actual value is {self.get_autofill()}.")

class PumpPHD2000_NoRefill(PumpPHD2000):
    """Create Pump object for Harvard PHD 2000 twin syringe pump.

    Parameters
    ----------
    chain : Chain
        Pump chain.
    address : int, optional
        Pump address. Default is 0.
    name : str, optional
        Used in logging. Default is PHD2000.
    """
    def __init__(self, chain:Chain, address:int=0, name:str='PHD2000'):
        super().__init__(chain,address,name)

    def __repr__(self):
        self.update_state()
        rep = f"PumpPHD2000_NoRefill Object (name = {self.name}) on <{str(self.serialcon)}> with address <{self.address}>.\n"
        rep += f"State: {self.state}, Mode: {self.mode}, Direction: {self.direction}, Parallel/Reciprocal: {self.parallel_reciprocal}"
        return rep

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

    def get_direction(self) -> str:
        """Get the current direction of the pump. This should always be INFUSE, since this pump has no refill mode.

        Returns
        -------
        str
            Can be INFUSE (outward flow) or REFILL (inward flow).
        """
        response = self.issue_command('DIR')
        return response[1]

    def set_direction(self, direction: str):
        """Set the direction of the pump.
        Will raise an 
        """
        raise PumpFunctionNotAvailable(f"{self.name}: This pump does not support changing pump direction")

    def set_refill_rate(self, flowrate:float, unit:str):
        raise PumpFunctionNotAvailable(f"{self.name}: This pump cannot refill, and thus a refill rate cannot be set.")
    
    def get_refill_rate(self) -> tuple[float,str]:
        raise PumpFunctionNotAvailable(f"{self.name}: This pump cannot refill, and thus a refill rate cannot be get.")

    def set_autofill(self, autofill:str):
        raise PumpFunctionNotAvailable(f"{self.name}: This pump cannot refill, and thus auto-fill mode is always OFF.")

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
    def __init__(self, chain:Chain, address:int=0, name:str='Model33'):
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

class PumpStallError(PumpError):
    """Raised when we detect the pump has stalled"""
    def __init__(self, message):
        super().__init__(message)
        
class PumpFunctionNotAvailable(PumpError):
    """Raised when we try to use a function a pump does not have (like refilling mode)"""
    def __init__(self, message):
        super().__init__(message)