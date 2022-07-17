from abc import abstractproperty
import sys
import os
import argparse
import cv2
import requests
import numpy as np
from urllib.parse import quote as urllib_parse_quote
import win32clipboard
from io import BytesIO
from PIL import Image
from time import strftime, localtime, time
import logging

'''
Timeline:
v4.-1: 2021 08 03
separated out the link parsing to better handle more diverse inputs
v4.0: 2021 08 06
now with proper logging to file and stream
fixed the fact there was no timeout for requests
added error catching for when a twitter api token is not found
'''

'''
TODO
add error handling for bad urls
there's a fixme related to urls and a couple todos
try to use the bigger images
'''

APP_NAME = "pymeme"
VERSION = 4
THOST = "https://catbox.moe/user/api.php"
WORKING_DIR = r"C:\Users\AZM\Documents\Python\pymeme"
PAD_VALUE = 15
IMG_FORMATS = ["png", "jpg", "jpeg"]
LOG_FILE = f'{APP_NAME}v{VERSION}log.txt'
REQUESTS_TIMEOUT = 5


def img_link_from_tweet(tweet_id, num=0):
    logging.log(logging.DEBUG, f"Tweet id is {tweet_id}")

    try:
        with open("twitterapitoken", mode="r") as r:
            twitter_api_bearer_token = r.read()
    except FileNotFoundError:
        logging.error("Could not find file: twitterapitoken, exiting")
        exit(2)


    headers = {'Authorization': f'Bearer {twitter_api_bearer_token}'}
    params = (
        ('ids', tweet_id),
        ('expansions', 'attachments.media_keys'),
        ('media.fields', 'url'),
    )

    logging.log(logging.INFO, "Requesting image url from twitter")
    request_from = "https://api.twitter.com/2/tweets"
    try:
        r = requests.get(request_from, params=params, headers=headers, timeout=REQUESTS_TIMEOUT)
    except requests.exceptions.Timeout as e:
        logging.log(logging.ERROR, f"Request timed out at {request_from}, exiting: {e}")
        exit(1)
    except requests.exceptions.RequestException as e:
        logging.log(logging.ERROR, f"Unspecific error when requesting from {request_from}, exiting: {e}")
        exit(1)

    try:
        l = r.json()["includes"]["media"][num]["url"]
    except IndexError:
        logging.log(logging.ERROR, f"IndexError when grabbing image url from multi image tweet, exiting")
        exit()
        
    logging.log(logging.INFO, f"Direct link to twitter image is {l}")
    return l

def twitter_link(l):
    # needed because sometimes twitter links have ?s= in the end
    l += "?" # idk if this wont break the link in some cases but ig we'll find out eventually
    num = 0
    # TODO pretty this if where it's when a tweet with multiple images is linked
    if "photo" in l:
        _,artist,_,digits,_,num = l[l.index("twitter"):l.index("?")].split("/")
    else:
        _,artist,_,digits = l[l.index("twitter"):l.index("?")].split("/")
    # gets name of the artist@twitter@tweetreference
    name = f"{artist}_twitter_{digits}_{num}"
    return img_link_from_tweet(digits, int(num)-1), name

def parseurl(url):
    ending = url.split("/")[-1]
    for format in IMG_FORMATS:
        if ending.endswith(format):
            return url, ending.split(".")[0]
    if "twitter.com" in url:
        return twitter_link(url)
    logging.log(logging.ERROR, "URL not recognised as an image, exiting")
    exit()

def url_to_cv2(url):
    logging.log(logging.INFO, f"Downloading image from {url}")
    try:
        resp = requests.get(url, stream = True, timeout=REQUESTS_TIMEOUT).raw
    except requests.exceptions.Timeout as e:
        logging.log(logging.ERROR, f"Request timed out at {url}, exiting: {e}")
        exit()
    except requests.exceptions.RequestException as e:
        logging.log(logging.ERROR, f"Unspecific error when requesting from {url}, exiting: {e}")
        exit()
    
    image = np.asarray(bytearray(resp.read()), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    return image

def main():
    t0 = time()
    os.chdir(WORKING_DIR)

    # parse input
    parser = argparse.ArgumentParser(description="Image memer")
    parser.add_argument("url", metavar="URL", type=str, help="link to image, supports twitter links")
    parser.add_argument("-text", type=str, nargs=2, default=[" ", "wow?"], help="top/bottom text for image")
    parser.add_argument("-show", type=int, default=1, help="show image at the end, 0 or 1 also disables sednging to clipboard")
    parser.add_argument("-log", type=str, default="INFO", help="set log level for console output, WARNING/INFO/DEBUG")
    parser.add_argument("-out", type=str, default="", help="name for the output file, leave empty for auto generated name")
    parser.add_argument("-savedir", type=str, help="absolute path to the location the files are saved to")
    args = parser.parse_args()

    # setting up logger to info on terminal and debug on file
    log_format=logging.Formatter(f'%(asctime)s {APP_NAME} v{VERSION} %(levelname)s:%(name)s:%(funcName)s %(message)s')
    
    file_handler = logging.FileHandler(filename=LOG_FILE, mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(getattr(logging, args.log.upper()))
    
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(stream_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    #logging.basicConfig(format=log_format, filename=f'{APP_NAME}v{VERSION}log.txt', level=logging.DEBUG)
    #logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    logging.debug(f"Started with arguments: {sys.argv}")

    topt = urllib_parse_quote(args.text[0])
    bott = urllib_parse_quote(args.text[1])

    # decode input into image link
    image_url, name = parseurl(args.url)

    image = url_to_cv2(image_url)

    # pad image
    logging.info(f"Original image is {image.shape}")
    # pre resize image to be 600 pixels on the smaller side
    scale = 1
    if image.shape[1] > image.shape[0]: # wider than tall, height has to go to 600 - pad
        scale = (600 - PAD_VALUE*2)/image.shape[0]
    else: # taller than wide, width has to go to 600 - prolly not normal pad amount
        scale = (600)/image.shape[1]
    
    height = int(image.shape[0] * scale)
    width = int(image.shape[1] * scale)
    dim = (width, height)
    resized_image = cv2.resize(image, dim, interpolation = cv2.INTER_AREA)

    logging.info(f"Resized image to {resized_image.shape}")

    bordered_image = cv2.copyMakeBorder(resized_image, PAD_VALUE, PAD_VALUE, 0, 0, cv2.BORDER_CONSTANT)
    logging.debug(f"Padded image to {bordered_image.shape}")

    # convert to bytes and upload to host
    logging.info("Encoding image")
    a,e = cv2.imencode('.png', bordered_image)
    i = e.tobytes()

    data = {
                'reqtype': (None, 'fileupload'),
                'fileToUpload': ('name.png', i)
            }

    logging.info("Uploading image to temporary host")

    try:
        l = requests.post(THOST, files=data, timeout=REQUESTS_TIMEOUT)
    except requests.exceptions.Timeout as e:
        logging.error(f"Request timed out at {THOST}, exiting: {e}")
        exit()
    except requests.exceptions.RequestException as e:
        logging.error(f"Unspecific error when requesting from {THOST}, exiting: {e}")
        exit()

    thost_image_link = l.text.strip()

    logging.info(f"Image uploaded to {thost_image_link}")
    
    # meme it
    meme_link = f"https://api.memegen.link/images/custom/{topt}/{bott}.png?background={thost_image_link}"
    # FIXME check if success on uploading image, need example of it breaking
    logging.info(f"Meme link at {meme_link}")
    memed_image = url_to_cv2(meme_link)
    logging.info(f"Memed image is {memed_image.shape}")

    # crop and done
    final_image = memed_image[PAD_VALUE:memed_image.shape[0]-PAD_VALUE, 0:memed_image.shape[1]]
    logging.info(f"Memed image cut to {final_image.shape}")
    
    if args.out != "":
        name = args.out
    name = name.replace("?", "")
    name += ".png"

    if args.show:
        cv2.imshow("image", final_image)

    if args.savedir:
        path = args.savedir + "\\" + name
        cv2.imwrite(path, final_image)
        logging.info(f"Saved to {path}")
    else:
        cv2.imwrite(f"imgs\\{name}", final_image)
        logging.info(f"Saved to {os.getcwd()}\\imgs\\{name}")

    if args.show:
        # send to windows clipboard
        image = Image.open(f"{os.getcwd()}\\imgs\\{name}")
        output = BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        logging.info("Sent to clipboard")

    logging.info(f"Took {time() - t0} seconds")
    
    if args.show:
        cv2.waitKey(0)
    
    logging.debug("Exited")

if __name__ == '__main__':
    main()