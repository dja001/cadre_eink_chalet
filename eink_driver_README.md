
Notes on making this work. 

This is the color 13.3in e-Paper with the HAT+ (E) connected to a Raspberry Pi 4b. 

Plug the HAT+ and extender to the display. 
From one random source on the internet, the connectors should work on both sides but idk. 
The black part of the connector to the FPC ribbon rotates to open the connector.  I openned it with a flat screwdriver. 
Everything is super delicate so be gentle. 

The code that worked for me was in the following git repo:

git@github.com:waveshareteam/e-Paper.git

an is (weirdly) located in: `E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/python/examples`


--------------------------

creating mamba env

download and install mamba
Miniforge3-Linux-aarch64.sh

mamba create -n eink_display_env
mamba activate eink_display_env
mamba install python numpy pillow matplotlib
# not on conda-forge
pip install spidev

-------------------------------------

latin modern font

sudo apt install fonts-lmodern
rm -rf ~/.cache/matplotlib
plt.rcParams['font.family'] = 'Latin Modern Roman'

