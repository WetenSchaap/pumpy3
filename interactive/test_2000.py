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
chain = pumpy3.Chain("com5",baudrate=9600,timeout=0.2)

pump1 = pumpy3.PumpPHD2000_NoRefill(chain, 3, name="pump1")


#%% Test the pump
pump1.stop() # stop the pump if it is running

# test gets
pump1.get_diameter()
pump1.get_direction()
pump1.get_autofill()
pump1.get_mode()
pump1.get_rate()
pump1.get_volume_delivered()
pump1.get_target_volume()
pump1.get_state()
pump1.update_state()

try:
	pump1.get_refill_rate()
except pumpy3.PumpFunctionNotAvailable:
	print("refill not funtioning as expected")


# test all sets
pump1.set_diameter(4.0)
pump1.set_rate(2.0, "ml/hr") # set the infusion rate to 2 ml/h
pump1.set_diameter(1.234)
pump1.set_mode("PMP")
pump1.set_target_volume(20)
pump1.reset_volume_delivered()

failing_funcs = (
	pump1.set_autofill,
	pump1.set_direction,
)

for func in failing_funcs:
	try:
		func("")
	except pumpy3.PumpFunctionNotAvailable:
		print("function failed succesfully")

pump1.run() # start the pump

print(pump1)

pump1.stop()

print("does everything look good?")



# %%
