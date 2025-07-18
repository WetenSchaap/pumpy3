# pumpy3

Using this Python 3 module you can control some of your Harvard Apparatus syringe pumps using your computer over an RS-232 interface.

Adapted from the [pumpy3 project by IridiumWasTaken](https://github.com/IridiumWasTaken/pumpy3) - I basically completely rewrote it, but it gave some handy pointers.

## Supported pumps and using RS-232

I have developed this package for the following pumps, which we have in our lab:

- [Harvard Apparatus PHD 2000 (Catalog no 70-2000 to 70-2023)](https://harvardapparatus.com/media/harvard/pdf/PHD2000.pdf)
- [Harvard Apparatus Model 33 (Catalog no 55-3333)](https://www.harvardapparatus.com/media/harvard/pdf/553333_Pump_33_Manual.pdf)

But any pump that follows roughly the same commands should be almost trivial to implement, see below. Specifically, the commandset is called "pump 22" or "pump 44"-style commands in the manual.

These pumps need to be connected to your PC using a very obscure RJ11-to-DB9 (or RJ11-to-serial) connector, see [this screenshot of the manual](./doc/connecting.png). I could not find anyone selling them, so if you don't have one, you will need to make one yourself (or ask someone to make on for you). Probably you will end up with the following connection:

> Computer -> USB-to-serial -> serial-to-RJ11 -> Pump

Pumps can be chained (so you need only one computer connection to control multiple pumps) using regular RJ11 or RJ12 cables, which you can luckily buy easily and cheaply.

> ⚠️ Do ***NOT*** use the *DB9*-looking port on the back of your pump. It looks like it should be suitable for RS232, but it is not actually usable!

## Features

You can perform any action you can perform using the buttons on the device. The only notable exceptions is the "programming" function in some PHD 2000-pumps, which feels unnessecary when you are using a computer anyway.

## Installation & Requirements

This module should work on Windows, Linux, macOS, although I mainly tested on a Windows 10 PC. Install the module by:

### Dependency manager (prefered)

You can also install this package by using `pip`, `poetry`, `conda` etc., but this package is not on PyPi, so you need to install directly from this repo. You can search for how to do this, for example with `pip`, you need to run:

    pip install git+https://github.com/WetenSchaap/pumpy3.git

### Simple download (also fine)

Download the [`pump.py`](./pumpy3/pump.py) file containing pump classes and place it in your working directory. Manually install the dependencies using `pip`: `pyserial`.

## Usage

This is an example for connecting one pump chain with three pumps (one pump attached to a PC, and three connections betweem pumps). Other examples can be found in the `./interactive` folder, which should cover all available functions. You can also read the `pump.py` file itsself, functions should be documented pretty well.

```python
import pumpy3
import time

# Initialise chain
chain = pumpy3.Chain(
    "COM2",         # Check COM-port manually
    baudrate=9600,  # The Baudrate must be set on your pumps manually, 9600 is typically the default.
    timeout=0.1     # Timeout of 0.1 sec always worked for me, maybe double or triple if any weird errors occur.
)

# Initialise pumps on the chain:
# Initialise pump model 33 with address = 1. Address must be set manually on the pumps. The name is just for logging.
pump1 = pumpy3.PumpModel33(chain, address=1, name="Derek")
# Initialise two PHD 2000 pumps with address 2 and 3.
# note that there are PHD 2000 pumps with and without refill, make sure to select the correct one to prevent weird errors.
pump2 = pumpy3.PumpPHD2000_NoRefill(chain, address=2, name="Janet")
pump3 = pumpy3.PumpPHD2000_Refill(chain, address=3, name="Michael")

pump1.set_diameter(5.18, syringe = 1)  # set diameter of syringe 1 of pump1
pump1.set_diameter(12.28, syringe = 2) # set diameter of syringe 1 of pump1
pump2.set_diameter(20.01)              # PHD2000 only has 1 syringe
pump3.set_diameter(18.23)

# settings for pump 1
pump1.set_mode("PRO")                # set to PROportional mode
pump1.set_direction("INF")           # set syringe 1 to INFuse
pump1.set_parallel_reciprocal("OFF") # set reciprocal direction (so syringe 2 retracts now)
pump1.set_rate(12.2, "ml/hr", syringe=1)     # set syringe 1 speed to 12.2 ml/h
pump1.set_rate(23.0, "ul/mn", syringe=2)     # set syringe 2 speed to 23 µl/min

# settings for pump 2 & 3
pump2.set_mode("PMP")                # set to PuMP mode
pump3.set_mode("PMP")
pump2.set_rate(2, "ml/hr")           # set speed to 2 ml/h
pump3.set_rate(50, "ul/hr")          # set speed to 50 µl/h

# start the pumps!
pump1.run()
pump2.run()
pump3.run()

time.sleep(4)

# stop the pumps!
pump1.stop()
pump2.stop()
pump3.stop()
```

## Implementing more pumps

This should be easy, even with limited Python knowledge. start by looking at the pump manual and:

1. Create a new pump class inheriting from `Pump`
2. Set the following parameters in the `__init__`:
   - `mode_conversion`: dict with the available modes that can be set.
   - `running_status`, `stopped_status`, and `stalled_status`: tuples containing symbols for each of the statuses
   - `syringe_selection` (only if syringes can be individually addressed)
   - `unit_conversion` (only if available units (ml/hr, ul/min, etc.) are different)
3. Implement things missing from the `Pump` class, or change things to the implemeted methods
4. Share the changes back so others can make use of them 🤝

You can look at the exisitng classes for hints. You can also ask for help!
