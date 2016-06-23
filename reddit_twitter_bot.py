# -*- coding: utf-8 -*-

'''
Copyright 2015 Randal S. Olson

This file is part of the reddit Twitter Bot library.

The reddit Twitter Bot library is free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your option)
any later version.

The reddit Twitter Bot library is distributed in the hope that it will be
useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
License for more details. You should have received a copy of the GNU General
Public License along with the reddit Twitter Bot library.
If not, see http://www.gnu.org/licenses/.
'''

import praw
import json
import requests
import tweepy
import time
import os
import urllib.parse
from glob import glob

# Place your Twitter API keys here

# https://github.com/rhiever/reddit-twitter-bot#dependencies

# date +%s | sha256sum | base64 | head -c 32 ; echo

# email / password / access_token / access_token_secret / consumer_key / consumer_secret / tag
ACCOUNTS = [
]

# Place the subreddit you want to look up posts from here
SUBREDDIT_TO_MONITOR = 'ProgrammerTIL'

# Place the name of the folder where the images are downloaded
IMAGE_DIR = 'img'

# Place the name of the file to store the IDs of posts that have been posted
POSTED_CACHE = 'posted_posts.txt'

SCORE_THREESHOLD = 3
DELAY_AFTER_TWEET = 30
T_CO_LINKS_LEN = 24  # https://dev.twitter.com/overview/t.co
TWEET_SUFFIX = ""

class FileBasedContainer():
    def __init__(self, filename):
        self.filename = filename
        self.create_file(filename)
        self.content = None

    def __enter__(self):
        self.get_content_from_file()
        return self

    def __exit__(self, type, value, traceback):
        self.save_content_in_file()

    @staticmethod
    def create_file(filename):
        if not os.path.exists(filename):
            with open(filename, 'w'):
                pass

    def get_content_from_file(self):
        with open(self.filename, 'r') as in_file:
            self.content = set(line.strip() for line in in_file)
            print('[bot] Cache read from %s (contains %d elements)' % (self.filename, len(self.content)))

    def save_content_in_file(self):
        with open(self.filename, 'w') as out_file:
            for c in sorted(self.content):  # sorting the file is just for human easiness
                out_file.write(str(c) + '\n')
        print('[bot] Cache saved in %s (contains %d elements)' % (self.filename, len(self.content)))

    def __contains__(self, elt):
        return elt in self.content

    def add(self, elt):
        print('[bot] Adding ' + str(elt) + ' in the cache')
        return self.content.add(elt)


def setup_connection_reddit(subreddit_name):
    ''' Creates a connection to the reddit API. '''
    print('[bot] Setting up connection with reddit')
    reddit_api = praw.Reddit('reddit Twitter tool monitoring {}'.format(subreddit_name))
    return reddit_api.get_subreddit(subreddit_name)


def tweet_creator(subreddit_info):
    ''' Looks up posts from reddit. '''
    print('[bot] Getting posts from reddit')

    # You can use the following "get" functions to get posts from reddit:
    #   - get_top(): gets the most-upvoted posts (ignoring post age)
    #   - get_hot(): gets the most-upvoted posts (taking post age into account)
    #   - get_new(): gets the newest posts
    #
    # "limit" tells the API the maximum number of posts to look up

    posts = []
    for submission in subreddit_info.get_hot(limit=30):
        if submission.score > SCORE_THREESHOLD:
            posts.append({
                'id': submission.id,
                'title': submission.title,
                # This stores a link to the reddit post itself
                # If you want to link to what the post is linking to instead, use
                # "submission.url" instead of "submission.permalink"
                'link': submission.permalink,
                # Store the url the post points to (if any)
                # If it's an imgur URL, it will later be downloaded and uploaded alongside the tweet
                'url': submission.url,
            })
    return posts


def strip_title(title, num_characters):
    ''' Shortens the title of the post to the 140 character limit. '''
    # How much you strip from the title depends on how much extra text
    # (URLs, hashtags, etc.) that you add to the tweet
    # Note: it sucks but some short url like data.gov will be replaced
    # by longer URLs. Long term solution could be to use urllib.parse
    # to detect those.
    return title if len(title) <= num_characters else title[:num_characters - 1] + '…'


def get_image(img_url):
    ''' Downloads i.imgur.com images that reddit posts may point to. '''
    if 'imgur.com' in img_url:
        file_name = os.path.basename(urllib.parse.urlsplit(img_url).path)
        img_path = IMAGE_DIR + '/' + file_name
        print('[bot] Downloading image at URL ' + img_url + ' to ' + img_path)
        resp = requests.get(img_url, stream=True)
        if resp.status_code == 200:
            with open(img_path, 'wb') as image_file:
                for chunk in resp:
                    image_file.write(chunk)
            # Return the path of the image, which is always the same since we just overwrite images
            return img_path
        else:
            print('[bot] Image failed to download. Status code: ' + resp.status_code)
    else:
        print('[bot] Post doesn\'t point to an i.imgur.com link')
    return None


def tweeter(apis, posts, posted_cache):
    ''' Tweets all of the selected reddit posts. '''
    for post in posts:
        post_id = post['id']
        if post_id in posted_cache:
            print('[bot] Already tweeted: {}'.format(str(post_id)))
        else:
            post_title = post['title']
            img_path = get_image(post['url'])
            extra_text = ' ' + post['link'] + TWEET_SUFFIX
            extra_text_len = 1 + T_CO_LINKS_LEN + len(TWEET_SUFFIX)
            if img_path:
                extra_text_len += T_CO_LINKS_LEN
            post_text = strip_title(post_title, 140 - extra_text_len) + extra_text
            print('[bot] About to post ' + post_text)
            for api, tag in apis:
                if post_title.lower().startswith(tag.lower()):
                    print('[bot] Posting this link on Twitter (tag = ' + tag + ')')
                    print(post_text)
                    if img_path:
                        print('[bot] With image ' + img_path)
                        api.update_with_media(filename=img_path, status=post_text)
                    else:
                        api.update_status(status=post_text)
            posted_cache.add(post_id)
            time.sleep(DELAY_AFTER_TWEET)


def get_api_obj(credentials):
    _, _, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, CONSUMER_KEY, CONSUMER_SECRET, tag = credentials
    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    return tweepy.API(auth), tag


def main():
    ''' Runs through the bot posting routine once. '''
    # If the tweet tracking file does not already exist, create it
    if not os.path.exists(IMAGE_DIR):
        os.makedirs(IMAGE_DIR)

    subreddit = setup_connection_reddit(SUBREDDIT_TO_MONITOR)

    apis = [get_api_obj(a) for a in ACCOUNTS]

    with FileBasedContainer(POSTED_CACHE) as posted_cache:
        while True:
            posts = tweet_creator(subreddit)
            tweeter(apis, posts, posted_cache)
            print('[bot] Going to sleep now')
            time.sleep(60 * 60)


    # Clean out the image cache
    for filename in glob(IMAGE_DIR + '/*'):
    	os.remove(filename)

if __name__ == '__main__':
    main()
