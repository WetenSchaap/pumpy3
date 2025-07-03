#%% set up before starting
import pumpy3
import logging
import time

# Set up logging
# Create handlers
file_handler = logging.FileHandler('20250701_PJMS01-001.log')
stream_handler = logging.StreamHandler()

# Set formatter
formatter = logging.Formatter('[%(asctime)s] %(levelname)-8s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Set level
file_handler.setLevel(logging.INFO)
stream_handler.setLevel(logging.INFO)

# Get root logger and add handlers
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove all handlers associated with the root logger object
if logger.hasHandlers():
	logger.handlers.clear()

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

#%%

chain = pumpy3.Chain("com5")
pump1 = pumpy3.PumpModel33(chain, 0, name="pump1")
pump2 = pumpy3.PumpModel33(chain, 1, name="pump2")


#%% Setup the pumps and define the ramp parameters
pump1.stop() # stop the pump if it is running
pump2.stop()
pump1.set_diameter(40.0,1)
pump1.set_diameter(40.0,2)
pump2.set_diameter(40.0,1)
pump2.set_diameter(40.0,2) 

pump1.set_mode("PRO") # set to PROportional mode
pump1.set_direction("INF") # set syringe 1 to INFuse
pump1.set_parallel_reciprocal("ON") # reciprocal direction (so syringe 2 follows syringe 1)
pump2.set_mode("PRO") # set to PROportional mode
pump2.set_direction("INF") # set syringe 1 to INFuse
pump2.set_parallel_reciprocal("ON") # reciprocal direction (so syringe 2 follows syringe 1)

pump1.log_all_parameters()
pump2.log_all_parameters()

pump2.set_rate(0, "ml/h", 2) # syringe 2 does not participate in the ramp


print(pump1)
print(pump2)

print("does everything look good?")

# define the ramp parameters

rates_to_visit = [0.25,0.50,0.75,1,1.5,2,2.5,3,4,5,6,8,10] # in ml/h
time_per_rate = 3600  # in seconds
print(f"Total time for ramp: {len(rates_to_visit) * time_per_rate / 3600} hours")
print(f"Expected volume required per syringe: {sum(rates_to_visit) * time_per_rate / 3600} ml")
print("If this sounds okay, run the next cell to start the ramp.")

#%% Actually run

logging.info("Ramp parameters:")
logging.info(f"Rates to visit: {rates_to_visit} ml/h")
logging.info(f"time per rate: {time_per_rate} seconds")
logging.info(f"Total time for ramp: {len(rates_to_visit) * time_per_rate / 3600} hours")
logging.info(f"Expected volume required per syringe: {sum(rates_to_visit) * time_per_rate / 3600} ml")

input("Press Enter to start the ramp...")

for rate in rates_to_visit:
    logging.info(f"Setting rate to {rate} ml/h")
    pump1.set_rate(rate, "ml/h", 1)
    pump1.set_rate(rate, "ml/h", 2)
    pump2.set_rate(rate, "ml/h", 1)
    pump1.run()
    pump2.run()
    # Sleep for the specified time per rate
    try:
        pump1.sleep_with_heartbeat(time_per_rate, error_wakeup=True)
        pump2.sleep_with_heartbeat(time_per_rate, error_wakeup=True)
    except pumpy3.PumpError as e:
        logging.error(f"One of the pumps has stalled: {e}")
        logging.info(f"Stopping the ramp (at {rate} ml/h) due to pump stall.")
        break

logging.info("Ramp completed. Stopping pumps.")
pump1.stop()
pump2.stop()


