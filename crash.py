import openai
from geopy.geocoders import Nominatim
import overpy
import streamlit as st
import streamlit_folium
from openai import OpenAI
import json

import pandas as pd
import numpy as np
import folium
import h3


# Part 0: Util functions -------------------------------------------------------------------------------
def get_h_index(x, level=7):
    """
    This function is only used for the events dataframe.
    """
    try:
        return h3.latlng_to_cell(x['lat'], x['lon'], level)
    except:
        return None


# Part 1: Set up env and load events data ---------------------------------------------------------------
client = OpenAI(api_key=OPENAI_API_KEY)
mapbox_url = 'https://api.mapbox.com/styles/v1/jbcollins4/cl6zj8j8n001014r7trqm8ha3/tiles/256/{z}/{x}/{y}@2x?access_token=pk.eyJ1IjoiamJjb2xsaW5zNCIsImEiOiJjbDZ6YmdrNncwMnNyM3ZyMTF1dHFnbmVyIn0.-cj_dcJBa9nyKmRXnmRbuA'
geolocator = Nominatim(user_agent="geo_mapper")
api = overpy.Overpass()

# Part 2: Prompt ----------------------------------------------------------------------------------------
CHAT_TEMPLATE = """
You are a claim adjuster in an auto insurance company.
You will be provided a detailed description of a crash scene that is related to a claim, and the reported city and state.
You will extract the following information from the description:
* does the description contain information about the street that the crash has happened? If so, then contain_street_information=True, otherwise False.
* if contain_street_information=True, what is the full address of the street name? Store the name in variable "street_name". Please unpack all the abbreviations in street_name. For example, s -> south, rd -> road, st -> street. 
If contain_street_information = False, street_name = ''.  
* if the user provided crash region which includes city and state information, combine "street_name" and the provided crash region to a full address and store it in "full_address". 
if user did not provide valid city and state information, set "full_address" = street_name. 
* does the description contain information about the direction that the driver is travelling? If so, then contain_travel_direction=True, otherwise False.
* if contain_travel_direction = True, what direction is it? Store the name in variable "travel_direction". If contain_travel_direction = False, travel_direction = ''. 
* what is the severity level of the crash? Categorize it as "low-severity", "mid-severity", and "high-severity". Store the information in variable "severity". 
Store the confidence of the categorization in variable "severity_confidence", which should be between 0 and 1. 
Provide reasoning for this severity estimate and store the content in another variable "severity_reasoning". 
* did the trip end in a sudden stop or did the driver continue to drive and pull over somewhere else? Store the information in variable "crash_scene_end_type", and give it either value "sudden_stop", or "trip_continues". 

Other relevant background information: 
In the claim description, the driver of your claim will be referred to as either "V1" or "Ni", whereas other parties involved in the crash might be referred to as V2.
Direction of travel will be described as NB or SB meaning it is travelling north-bound or south-bound.


The output should be in the format 
{'contain_street_information': contain_street_information,
'contain_travel_direction': contain_travel_direction,
'street': street_name, 
'full_address': full_address,
'severity_level': severity,
'severity_confidence': severity_confidence,
'severity_reasoning': severity_reasoning, 
'travel_direction': travel_direction,
'crash_scene_end_type': sudden_stop or trip_continues}
"""

# Part 3: Strealint app and excecuted code
# Set the app title and description
st.set_page_config(layout="wide", page_title="OSM Overpass Query App", page_icon=":earth_africa:")
st.title(":cat: CMT Crash Claim Labeller :cat:")
st.write("Hello! :wave: This is Henry, a crash claim labeller!")
st.write("Please provide the claim description that you want me to help label.")
st.write("I'll generate a map with the matched trip that I have found for you to verify.")
st.write(" ")
# Define the layout of the app
col1, col2 = st.columns([1, 1])

with col1:
    user_chat = st.text_area("What can I help you label? :nerd_face:")

    if st.button("Ask"):
        response = client.chat.completions.create(model="gpt-3.5-turbo", # model="gpt-4-turbo-preview",
            messages=[{"role": "system", "content": CHAT_TEMPLATE}, {'role': 'user', 'content': user_chat}],
            max_tokens=1024, n=1, temperature=0.5, top_p=1, frequency_penalty=0.0, presence_penalty=0.6, )
        response_dict = json.loads(response.model_dump_json())

        result_dict = eval(response_dict['choices'][0]['message']['content'])
        # For debugging
        # st.write(response['choices'][0]['message']['content'])
        location = geolocator.geocode(result_dict['full_address'])

        if location:
            # Display the coordindate of the address
            if result_dict['contain_street_information'] and location:
                st.write(
                    f":collision: From the description, I have identified that the crash happened on this street: **{result_dict['full_address']}** \n "
                )
                if result_dict['travel_direction']:
                    st.write(f":car: Before the crash happened, the driver was traveling in this direction: **{result_dict['travel_direction']}**."
                    )
                st.write(
                    f":exclamation: The crash incident can be categorized as **{result_dict['severity_level']}** with {int(result_dict['severity_confidence']*100)}% confidence."
                )
                st.write(':sparkles: The reasoning for this categorization is as follow: ')
                st.write('\t', result_dict['severity_reasoning'])

                if result_dict['crash_scene_end_type'] == 'trip_continues':
                    st.write(
                        f":octagonal_sign: After the crash, the driver did not come to a sudden stop but continued to drive."
                    )
                else:
                    st.write(":octagonal_sign: After the crash, the drive came to a sudden stop and did not continue to drive. ")
            elif result_dict['contain_street_information']  and not location:
                st.write(
                    f":collision: From the description, I have identified that the crash happened on this road: **{result_dict['full_address']}** \n "
                    f":cry: However, I cannot locate this road in the OSM dataset"
                    )
            elif not result_dict['contain_street_information']:
                st.write(
                    f":cry: From the description, I cannot identify any information about the street on which the crash happened."
                )

            # crash_ad, and highway_441 are obtained in Databricks
            # Notebook: (20240229_Claim_labeller) https://cmt-cmt-statefarm-data-science-prd.cloud.databricks.com/?o=1571324165501902#notebook/154780448962512/command/154780448962513
            crash_ad = pd.read_csv("crash/crash_ad.csv")
            crash_ad.rename(columns={'mm_lat': 'lat', 'mm_lon': 'lon'}, inplace=True)
            crash_ad['h3_12'] =  crash_ad.apply(lambda x: get_h_index(x, level=10), axis=1)
            highway = pd.read_csv("crash/highway_441.csv")
            highway['h3_12'] =  highway.apply(lambda x: get_h_index(x, level=10), axis=1)
            highway.sort_values(by='lat', inplace=True)
            st.write(f":palm_tree: The START latitude and longitude of the road is ({highway.lat.iloc[0]}, {highway.lon.iloc[0]})")
            st.write(f":palm_tree: The END latitude and longitude of the road is ({highway.lat.iloc[-1]}, {highway.lon.iloc[-1]})")

            st.markdown("""---""")

            st.write(f":smile_cat: :smiley_cat: :heart_eyes_cat: Found one potential crash trip with driveid = **FABC98FE-C422-4D5B-91CA-AEB733813909**"
            )
            st.write(
                f":clock1: The reported loss date is **2023-01-30 19:00:00**"
            )
            st.write(f":clock1: The matched trip ended at **2023-01-30 20:32:51**")
            
            # map plotting 
            with col2: 
                way_h3_12 = set(highway.h3_12)
                crash_ad['is_highway'] = crash_ad.apply(lambda x: x['h3_12'] in way_h3_12, axis=1)
                mean_latlon = crash_ad[['lat', 'lon']].values.mean(axis=0).tolist()
                m = folium.Map(location=mean_latlon, zoom_start=13, tiles=mapbox_url, attr='JBC', width=600, height=600)
                for i in range(crash_ad.shape[0]): 
                    marker_color = 'red' if crash_ad.is_highway.iloc[i] else 'blue'
                    folium.Circle(location=[crash_ad.lat.iloc[i], crash_ad.lon.iloc[i]], radius=2, color=marker_color, 
                            fill=True, fill_color=marker_color, tiles=mapbox_url, attr='JBC').add_to(m)
                streamlit_folium.folium_static(m)

                def verify(flag):
                    if flag:
                        st.write('Saved this trip-claim pair as an auto-matched record.')
                    else:
                        st.write('Moved this claim to the manual-labeling pipeline.')

                m = st.markdown("""
                <style>
                div.stButton > button:first-child {
                    background-color: #0099ff;
                    color:#ffffff;
                }
                div.stButton > button:hover {
                    background-color: #00ff00;
                    color:#ff0000;
                    }
                </style>""", unsafe_allow_html=True
                                )
                st.button("Looks like a good match")
                st.button("Does not look like a match")
