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

#%%

chain = pumpy3.Chain("com5",baudrate=9600,timeout=0.05)
pump1 = pumpy3.PumpModel33(chain, address=1, name="pump1")
pump2 = pumpy3.PumpModel33(chain, address=2, name="pump2")

#%% Test the pump
pump1.stop() # stop the pump if it is running
pump2.stop() # stop the pump if it is running

pump1.set_diameter(1, 1) # this is a 1 mm diameter syringe
pump1.set_diameter(2, 2) 
pump2.set_diameter(34, 1) 
pump2.set_diameter(43, 2) 
pump1.set_mode("PRO") # set to PROportional mode
pump2.set_mode("PRO")
pump1.set_direction("INF") # set syringe 1 to INFuse
pump2.set_direction("INF")
pump1.set_parallel_reciprocal("ON") # non-reciprocal direction
pump1.set_parallel_reciprocal("ON")
pump1.set_rate(1200.2, "ul/hr", 1) 
pump1.set_rate(23, "ul/mn", 2)
pump2.set_rate(23, "ml/hr", 1) 
pump2.set_rate(2, "ml/mn", 2) 

print(pump1)

pump1.log_all_parameters()

print("does everything look good?")

#%% Actually run
pump1.run()
