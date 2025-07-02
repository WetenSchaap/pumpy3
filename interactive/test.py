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
logging.debug('This is a debug message')
logging.info('This is an info message')
logging.warning('This is a warning message')
logging.error('This is an error message')
logging.critical('This is a critical message')


#%%

chain = pumpy3.Chain("com5")
pump1 = pumpy3.PumpModel33(chain, 0, name="pump1")

#%% Test the pump
pump1.stop() # stop the pump if it is running
pump1.set_diameter(4.0, 1) # this is a 1 mm diameter syringe
pump1.set_diameter(4.0, 2) # this is a 1 mm diameter syringe
pump1.set_mode("PRO") # set to PROportions mode
pump1.set_direction("INF") # set syringe 1 to INFuse
pump1.set_parallel_reciprocal("OFF") # reciprocal direction (so syringe 2 retracts now)
pump1.set_rate(1, "ml/h", 1) # set speed to 1 ml/h
pump1.set_rate(2, "ml/h", 2) # set speed to 2 ml/h

print(pump1)

print("does everything look good?")

#%% Actually run
pump1.run()
