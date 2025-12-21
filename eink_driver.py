
import sys
from pathlib import Path
import logging
from PIL import Image

# driver for eink display is in a separate git depot
EPD_LIB = Path("/home/pilist/bin/e-Paper/E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/python/lib")

if str(EPD_LIB) not in sys.path:
    sys.path.insert(0, str(EPD_LIB))

def eink_update(image_path: str, 
                test_mode: bool = False) -> None:
    """Update e-ink display with given image"""
    logging.info(f"Updating e-ink display with: {image_path}")

    import os
    import shutil
    import tempfile
    
    src = image_path
    dst = 'figures/current_image.png'
    
    tmp = dst + '.tmp'
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)   # atomic on Linux

    # eink update is not done in test mode
    if not test_mode:
        import epd13in3E
        epd = epd13in3E.EPD()
        try:
            epd.Init()
            logging.info("clearing...")
            epd.Clear()

            logging.info("2.show image file")
            Himage = Image.open(image_path)
            epd.display(epd.getbuffer(Himage))

            epd.sleep()
        except:
            logging.exception("Something went wrong")
            epd.sleep()

def eink_clear(test_mode) -> None:
    """Clear e-ink display"""
    logging.info("Clearing e-ink display")

    # eink update is not done in test mode
    if not test_mode:
        import epd13in3E
        epd = epd13in3E.EPD()
        try:
            epd.Init()
            logging.info("clearing...")
            epd.Clear()

            epd.sleep()
        except:
            print("Error clearing image goto sleep...")
            epd.sleep()


if __name__ == '__main__':

    import logging
    logging.basicConfig(level=logging.DEBUG)

    test_figure = './figures/current_image.png'
    eink_update(test_figure, test_mode=False)
