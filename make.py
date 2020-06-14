#!/usr/bin/env python
# coding: utf-8

import argparse, json, sqlite3, os, glob, time, sys, requests, random, glob, webbrowser, utils
from selenium import webdriver
from selenium.common import exceptions
from datetime import datetime
from geojson import Feature, FeatureCollection, Point
from sys import stdout
os.system('cls' if os.name == 'nt' else 'clear')

#Set up environment
if os.path.exists('.env'):
    fb_user = os.getenv('fb_user')
    fb_pass = os.getenv('fb_pass')
    mapbox_token = os.getenv('mapbox_token')
    print('>> Loaded credentials from .env file.')
else:
    print("Welcome! Let's set up your environment. This will create a .env file in the same folder as this script, and set it up with your email, password, and Mapbox API Key. This is saved only on your device and only used to autofill the Facebook login form.\n")

    fb_user = input("Facebook Email Address: ")
    fb_pass = input("Facebook Password: ")
    print("\nTo plot your friends on a map, you need a (free) Mapbox API Key. If you don't already have one, follow instructions at https://docs.mapbox.com/help/glossary/access-token, then come back here to enter the access token\n")
    mapbox_token = input("Mapbox access token: ")

    f = open(".env","w+")
    f.write('fb_user="' + fb_user + '"\n')
    f.write('fb_pass="' + fb_pass + '"\n')
    f.write('mapbox_token="' + mapbox_token + '"\n')
    f.close()

    print("\nGreat! Details saved in .env, so you shouldn't need to do this again.\n")

# Prepare database
friends_html = 'db/friend_list.html'
profiles_dir = 'db/profiles/'
db_geojson = "db/points.geojson"

db_index = 'friend_list'
db_profiles = 'profiles'
db_locations = 'locations'

if not os.path.exists(profiles_dir):
    os.makedirs(profiles_dir)

# Configure browser
def start_browser():
    # Ensure mobile-friendly view for parsing
    useragent = "Mozilla/5.0 (Linux; Android 8.0.0; Pixel 2 XL Build/OPD1.170816.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Mobile Safari/537.36"

    #Firefox
    profile = webdriver.FirefoxProfile()
    profile.set_preference("general.useragent.override", useragent)
    options = webdriver.FirefoxOptions()
    options.set_preference("dom.webnotifications.serviceworker.enabled", False)
    options.set_preference("dom.webnotifications.enabled", False)
    options.add_argument('--headless')

    browser = webdriver.Firefox(firefox_profile=profile,options=options)
    return browser

# Login
def sign_in():
    fb_start_page = 'https://m.facebook.com/'
    print("Logging in %s automatically..." % fb_user)
    browser.get(fb_start_page)
    email_id = browser.find_element_by_id("m_login_email")
    pass_id = browser.find_element_by_id("m_login_password")
    confirm_id = browser.find_element_by_name("login")
    email_id.send_keys(fb_user)
    pass_id.send_keys(fb_pass)
    confirm_id.click()

    time.sleep(3)
    return True

# Download friends list
def download_friends_list():
    browser.get("https://m.facebook.com/me/friends")
    time.sleep(3)
    print('Loading friends list...')
    scrollpage = 1
    while browser.find_elements_by_css_selector('#m_more_friends'):
        browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        stdout.write("\r>> Scrolled to page %d" % (scrollpage))
        stdout.flush()
        scrollpage += 1
        time.sleep(1)

    with open (friends_html, 'w', encoding="utf-8") as f:
        f.write(browser.page_source)
        print("\n>> Saved friend list to '%s'" % friends_html)

# Parse friends list into JSON
def index_friends():
    friends = utils.db_read(db_index)
    already_parsed = []
    for i,d in enumerate(friends):
        already_parsed.append(d['id'])
    print('Loading saved friends list...')
    browser.get('file:///' + os.getcwd() + '/' + friends_html)
    base = '(//*[@data-sigil="undoable-action"])'
    num_items = len(browser.find_elements_by_xpath(base))
    if num_items == 0:
        print("\nWasn't able to parse friends index. This probably means that Facebook updated their template. \nPlease raise issue on Github and I will try to update the script. \nOr if you can code, please submit a pull request instead :)\n")
        sys.exit()
    for i in range(1,num_items+1):
        b = base + '['+str(i)+']/'
        info = json.loads(browser.find_element_by_xpath(b+'/div[3]/div/div/div[3]').get_attribute('data-store'))
        stdout.write("\rScanning friend list... (%d / %d)" % (i,num_items))
        stdout.flush()
        if not info['id'] in already_parsed:
            alias = '' if info['is_deactivated'] else browser.find_element_by_xpath(b+'/div[2]//a').get_attribute('href')[8:]
            d = {
                'id': info['id'],
                'name': browser.find_element_by_xpath(b+'/div[2]//a').text,
                'is_deactivated': info['is_deactivated'],
                'alias': alias,
                'photo_url': browser.find_element_by_xpath(b+'div[1]/a/i').get_attribute('style').split('("')[1].split('")')[0],
                }
            stdout.write('\r>> Added %s (#%s)                             \n' % (d['name'],i))
            stdout.flush()

            utils.db_write(db_index,d)

    print('\n>> Saved friends list (%s) to %s' % (num_items,db_index))

# Download profile pages
def download_profiles():
    print('Downloading profiles...')
    session_downloads = 0
    index = utils.db_read(db_index)
    for i,d in enumerate(index):
        if not d['is_deactivated']:
            fname = profiles_dir + str(d['id']) + '.html'
            if not os.path.exists(fname):
                print('- %s (# %s)' % (d['name'],d['id']))
                browser.get('https://mbasic.facebook.com/profile.php?v=info&id='+str(d['id']))
                session_downloads += 1
                time.sleep(random.randint(1,3))
                if session_downloads == 45:
                    print("Taking a voluntary break at " + str(session_downloads) + " profile downloads to prevent triggering Facebook's alert systems. I recommend you quit (Ctrl-C or quit this window) to play it safe and try coming back tomorrow to space it out. \nOr, press enter to continue at your own risk.")
                if browser.title == "You can't use this feature at the moment":
                    print("\n***WARNING***\n\nFacebook detected abnormal activity, so this script is going play it safe and take a break.\n- As of March 2020, this seems to happen after downloading ~45 profiles in 1 session.\n- I recommend not running the script again until tomorrow.\n- Excessive use might cause Facebook to get more suspicious and possibly suspend your account.\n\nIf you have experience writing scrapers, please feel free to recommend ways to avoid triggering Facebook's detection system :)")
                    sys.exit(1)
                if browser.find_elements_by_css_selector('#login_form') or browser.find_elements_by_css_selector('#mobile_login_bar'):
                    print('\nBrowser is not logged into facebook! Please run again to login & resume.')
                    sys.exit(1)
                else:
                    with open (fname, 'w', encoding="utf-8") as f:
                        f.write(browser.page_source)

# Parse profile pages into JSON
def parse_profile(profile_file):
    sections = {
        'tagline': {'txt':'//*[@id="root"]/div[1]/div[1]/div[2]/div[2]'},
        'about': {'txt':'//div[@id="bio"]/div/div/div'},
        'quotes': {'txt':'//*[@id="quote"]/div/div/div'},
        'rel': {'txt':'//div[@id="relationship"]/div/div/div'},
        'rel_partner': {'href':'//div[@id="relationship"]/div/div/div//a'},
        'details': {'table':'(//div[not(@id)]/div/div/table[@cellspacing]/tbody/tr//'},
        'work': {'workedu':'//*[@id="work"]/div[1]/div/div'},
        'education': {'workedu':'//*[@id="education"]/div[1]/div/div'},
        'family': {'fam':'//*[@id="family"]/div/div/div'},
        'life_events': {'years':'(//div[@id="year-overviews"]/div/div/div/div/div)'}
    }

    profile_id = int(os.path.basename(profile_file).split('.')[0])
    profile_path = 'file://' + os.getcwd() + '/' + profile_file
    
    browser.get(profile_path)
    x = browser.find_element_by_xpath
    xs = browser.find_elements_by_xpath
    alias = x('//a/text()[. = "Timeline"][1]/..').get_attribute('href')[8:].split('?')[0]
    d = {
        'id': profile_id,
        'name': browser.title,
        'alias': alias if alias !='profile.php' else '',
        'meta_created' : time.strftime('%Y-%m-%d', time.localtime(os.path.getctime(profile_file)))
    }

    print('>> Parsing: %s (# %s)' % (d['name'], d['id']))

    for k,v in sections.items():
        try:
            if 'src' in v:
                d[str(k)] = x(v['src']).get_attribute('src')
            elif 'txt' in v:
                d[str(k)] = x(v['txt']).text
            elif 'href' in v:
                d[str(k)] = x(v['href']).get_attribute('href')[8:].split('?')[0]
            elif 'table' in v:
                d['details'] = []
                rows = xs(v['table']+'td[1])')
                for i in range (1, len(rows)+1):
                    deets_key = x(v['table']+'td[1])'+'['+str(i)+']').text
                    deets_val = x(v['table']+'td[2])'+'['+str(i)+']').text
                    d['details'].append({deets_key:deets_val})
            elif 'workedu' in v:
                d[str(k)] = []
                base = v['workedu']
                rows = xs(base)
                for i in range (1, len(rows)+1):
                    dd = {}
                    dd['link'] = x(base+'['+str(i)+']'+'/div/div[1]//a').get_attribute('href')[8:].split('&')[0].split('/')[0]
                    dd['org'] = x(base+'['+str(i)+']'+'/div/div[1]//a').text
                    dd['lines'] = []
                    lines = xs(base+'['+str(i)+']'+'/div/div[1]/div')
                    for l in range (2, len(lines)+1):
                        line = x(base+'['+str(i)+']'+'/div/div[1]/div'+'['+str(l)+']').text
                        dd['lines'].append(line)
                    d[str(k)].append(dd)
            elif 'fam' in v:
                d[str(k)] = []
                base = v['fam']
                rows = xs(base)
                for i in range (1, len(rows)+1):
                    d[str(k)].append({
                        'name': x(base+'['+str(i)+']'+'//h3[1]').text,
                        'rel': x(base+'['+str(i)+']'+'//h3[2]').text,
                        'alias': x(base+'['+str(i)+']'+'//h3[1]/a').get_attribute('href')[8:].split('?')[0]
                    })
            elif 'life_events' in k:
                d[str(k)] = []
                base = v['years']
                years = xs(base)
                for i in range (1,len(years)+1):
                    year = x(base+'['+str(i)+']'+'/div[1]').text
                    events = xs(base+'['+str(i)+']'+'/div/div/a')
                    for e in range(1,len(events)+1):
                        event = x('('+base+'['+str(i)+']'+'/div/div/a)'+'['+str(e)+']')
                        d[str(k)].append({
                            'year': year,
                            'title': event.text,
                            'link': event.get_attribute('href')[8:].split('refid')[0]
                        })
            
        except exceptions.NoSuchElementException:
            pass

    return d

# Parse all unparsed profiles in db profile folder
def parse_profile_files():
    already_parsed = []
    profiles = utils.db_read(db_profiles)
    for profile in profiles:
        already_parsed.append(profile['id'])

    profile_files = glob.glob(profiles_dir+'*.html')
    for profile_file in profile_files:
        profile_id = int(os.path.basename(profile_file).split('.')[0])
        if not profile_id in already_parsed:
            profile = parse_profile(profile_file)
            profiles.append(profile)
            utils.db_write(db_profiles,profile)
    
    print('>> %s profiles parsed to %s' % (len(profile_files),db_profiles))

# Create index of friends and their locations
def index_locations():
    print("Scanning profiles for location (eg. current city)...")
    profiles = utils.db_read(db_profiles)
    
    for p in profiles:
        details = json.loads(p['details'])
        loc = ''
        for d in details:
            if d.get('Address'):
                loc = d.get('Address')
        for d in details:
            if d.get('Current City'):
                loc = d.get('Current City')  
                
        if loc != '':
            utils.db_update(db_profiles,p['id'],{'location': loc})
    
    print('>> Updated friend locations')

# Get coordinates for all locations
def make_map():
    print('Geocoding locations from profiles...')
    url_base = 'https://api.mapbox.com/geocoding/v5/mapbox.places/'

    profiles = utils.db_read(db_profiles)
    locations = utils.db_read(db_locations)
    
    geo_dict = {}
    for location in locations:
        geo_dict[location['location']] = location['coordinates']
    
    features = []
    for d in profiles:
        if d['location'] is not None:
            stdout.write("\r>> Geocoding %s                         " % (d['location']))
            stdout.flush()
            if d['location'] in geo_dict:
                coordinates = json.loads(geo_dict[d['location']])
            else:
                r = requests.get(url_base + d['location'] + '.json', params={
                    'access_token': mapbox_token,
                    'types': 'place,address',
                    'limit': 1
                })
                try:
                    coordinates = r.json()['features'][0]['geometry']['coordinates']
                except IndexError:
                    pass

                utils.db_write(db_locations,{'location': d['location'],'coordinates': coordinates})
                geo_dict[d['location']] = str(coordinates)

            features.append(Feature(
                geometry = Point(coordinates),
                properties = {'name': d['name'],'location': d['location'],'id': d['id']}
            ))

            collection = FeatureCollection(features)
            with open(db_geojson, "w") as f:
                f.write('%s' % collection)

    with open('template-map.html') as f:
        html=f.read()
        html=html.replace('{{mapbox_token}}', mapbox_token)
        html=html.replace('{{datapoints}}', str(collection))
    with open('friends-map.html', "w", encoding="utf-8") as f:
        f.write(html)
    print('>> Saved map to friends-map.html!')
    webbrowser.open_new('file://' + os.getcwd() + '/friends-map.html') 

# Shell application
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Facebook friends profile exporter')
    parser.add_argument('--index', action='store_true', help='Index friends list')
    parser.add_argument('--download', action='store_true', help='Download friends profiles')
    parser.add_argument('--parse', action='store_true', help='Parse profiles to database')
    parser.add_argument('--map', action='store_true', help='Make the map!')
    parser.add_argument('--json', action='store_true', help='Export database to JSON files')
    args = parser.parse_args()
    browser = start_browser()
    signed_in = False
    try:
        fullrun = True if len(sys.argv) == 1 else False

        #Index friends list
        if fullrun or args.index:
            signed_in = sign_in()
            if not signed_in: sign_in()
            download_friends_list()
            index_friends()

        #Download profiles
        if fullrun or args.download:
            if not signed_in: sign_in()
            download_profiles()

        #Parse profiles
        if fullrun or args.parse:
            parse_profile_files()

        #Geocode
        if fullrun or args.map:
            index_locations()
            make_map()

        #JSON Export (Optional)
        if fullrun or args.json:
            utils.db_to_json()

    except KeyboardInterrupt:
        print('\nThanks for using the script! Please raise any issues on Github.')
        pass