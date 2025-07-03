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
pump1 = pumpy3.Pump2000(chain, 0, name="pump1")

#%% Test the pump
pump1.stop() # stop the pump if it is running
pump1.setdiameter(4.0)
pump1.setinfusionrate(2.0, "m/h") # set the infusion rate to 2 ml/h
pump1.infuse() # start the pump

print(pump1)

print("does everything look good?")

#%% Actually run
pump1.run()
