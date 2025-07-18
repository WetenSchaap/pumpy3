#%% set up before starting
import pumpy3
import logging
import time

# Set up logging
# Create handlers
file_handler = logging.FileHandler('pumpy3.log')
stream_handler = logging.StreamHandler()

# Set formatter
formatter = logging.Formatter('[%(asctime)s] %(levelname)-8s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Set level
file_handler.setLevel(logging.DEBUG)
stream_handler.setLevel(logging.DEBUG)

# Get root logger and add handlers
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Remove all handlers associated with the root logger object
if logger.hasHandlers():
	logger.handlers.clear()

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# Example log messages
# logging.debug('This is a debug message')
# logging.info('This is an info message')
# logging.warning('This is a warning message')
# logging.error('This is an error message')
# logging.critical('This is a critical message')


#%%

chain = pumpy3.Chain("com5",baudrate=9600,timeout=0.1)
pump1 = pumpy3.PumpModel33(chain, address=1, name="pump1")

#%% Test the pump

pump1.stop() # stop the pump if it is running
time.sleep(1)
pump1.set_diameter(18.08, 1) # this is a 1 mm diameter syringe
time.sleep(1)

pump1.set_diameter(02.01, 2) # this is a 1 mm diameter syringe
time.sleep(1)

pump1.set_mode("PRO") # set to PROportional mode
time.sleep(1)

pump1.set_direction("INF") # set syringe 1 to INFuse
time.sleep(1)

pump1.set_parallel_reciprocal("OFF") # reciprocal direction (so syringe 2 retracts now)
time.sleep(1)

pump1.set_rate(12.2, "ml/hr", 1) # set speed to 1 ml/h
time.sleep(1)

pump1.set_rate(23, "ul/mn", 2) # set speed to 2 ml/h
time.sleep(1)


print(pump1)

pump1.log_all_parameters()
pump1.log_all_settings()
print("does everything look good?")

#%% Actually run
pump1.run()
