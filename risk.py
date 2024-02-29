import openai
from geopy.geocoders import Nominatim
import overpy
import streamlit as st
import streamlit_folium

import pandas as pd
import numpy as np
from scipy.spatial import ConvexHull
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
openai.api_key = "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"
mapbox_url = 'https://api.mapbox.com/styles/v1/jbcollins4/cl6zj8j8n001014r7trqm8ha3/tiles/256/{z}/{x}/{y}@2x?access_token=pk.eyJ1IjoiamJjb2xsaW5zNCIsImEiOiJjbDZ6YmdrNncwMnNyM3ZyMTF1dHFnbmVyIn0.-cj_dcJBa9nyKmRXnmRbuA'
geolocator = Nominatim(user_agent="geo_mapper")
api = overpy.Overpass()

df_events = pd.read_parquet("/Users/fguo/cmt/ChatGeoPT/events_data/us_prod_events_hindex.parquet")

# Part 2: Prompt ----------------------------------------------------------------------------------------
CHAT_TEMPLATE = """Assistant gets the address and task from the user's question. 
  If the task is to get the corrdinates for the address, then Coordinate=True, otherwise False.
  If the task is to get the risk level around the address, then Risk=True, otherwise False.
  If the task is to get the way id and there is a required radius, then Way_id is equal to the required radius, otherwise Way_id=100. If the task is not to get way id, then Way_id=0. 
  If the task is to get the node id and there is a required radius, then Node_id is equal to the required radius, otherwise Node_id=100. If the task is not to get node id, then Node_id=0. 
  The output should be in the format {'Coordinate'=True, 'Address': address, 'Risk': Risk, 'Way_id': Way_id, 'Node_id': Node_id}"""

# Part 3: Strealint app and excecuted code 
# Set the app title and description
st.set_page_config(layout="wide", page_title="OSM Overpass Query App", page_icon=":earth_africa:")
st.title(":cat: OSM Risk Expert :cat:")
st.write("Hello! :wave: I'm Henry, your personalized driving assistant and osm expert!" 
         "Feel free to ask questions about the road safety around your neighborhood. I'll generate a map to show the safety levels."
         "If you are a technical person, feel free to ask for the osm way id and node id given an address.")

# Define the layout of the app
col1, col2 = st.columns([1, 1])
with col1:
    user_chat = st.text_area("What can I help you find? :thinking_face:")

    if st.button("Ask"):
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": CHAT_TEMPLATE},
                    {'role': 'user', 'content': user_chat}],
            max_tokens=1024,
            n=1,
            temperature=0.5,
            top_p=1,
            frequency_penalty=0.0,
            presence_penalty=0.6,
        )

        chatout = eval(response['choices'][0]['message']['content'])
        # For debugging
        # st.write(response['choices'][0]['message']['content'])
        location = geolocator.geocode(chatout['Address'])
        
        if location: 
            # Display the coordindate of the address 
            if chatout['Coordinate'] == True: 
                st.write(f"The latitude and longitude for the given address is ({location.latitude}, {location.longitude})")
            
            # Display the wayid around the address. 
            if chatout['Way_id'] > 0 or chatout['Node_id'] > 0:
                # Formulate the Overpass query to find the nearest way to the given coordinates
                overpass_query = f"""
                way(around:{chatout['Way_id']}, {location.latitude}, {location.longitude})['highway'];
                (._;>;);
                out body;
                """
                result = api.query(overpass_query)

                way_plots = {"way_id": [], 'start_node_id':[], 'start_node_lat': [], 'start_node_lon': [], 
                             'end_node_id':[], 'end_node_lat': [], 'end_node_lon': []}
                for way in result.ways: 
                    way_id = way.id 
                    way_plots["way_id"].append(way_id)

                    way_nodes = way.nodes
                    start_nodes = way_nodes[0]
                    end_nodes = way_nodes[-1]
                    way_plots['start_node_id'].append( float(way_nodes[0].id) )
                    way_plots['start_node_lat'].append( float(way_nodes[0].lat) )
                    way_plots['start_node_lon'].append( float(way_nodes[0].lon) )
                    way_plots['end_node_id'].append( float(way_nodes[-1].id) )
                    way_plots['end_node_lat'].append( float(way_nodes[-1].lat) )
                    way_plots['end_node_lon'].append( float(way_nodes[-1].lon) )
                if not chatout['Risk']:
                    st.write("""Way_id includes {}""".format(",".join(["{}".format(x) for x in way_plots['way_id']])))
                way_plots = pd.DataFrame(way_plots)
                if not chatout['Risk']:
                    st.write("""Detailed way id information is stored in the folder "wayid_outputs" """)
                    way_plots.to_csv("/Users/fguo/cmt/ChatGeoPT/wayid_outputs/wayid_summary.csv", index=False)

                # Define the map 
                with col2:
                    if not chatout['Risk']:
                        m = folium.Map(location=[location.latitude, location.longitude], zoom_start=16, tiles=mapbox_url, attr='JBC', width=600, height=600)
                        folium.Circle(location=[location.latitude, location.longitude], radius=10, color='black', 
                                    fill=True, fill_color='black', tiles=mapbox_url, attr='JBC').add_to(m)
                        for i in range(way_plots.shape[0]): 
                            folium.PolyLine([[way_plots.start_node_lat.iloc[i], way_plots.start_node_lon.iloc[i]], 
                                            [way_plots.end_node_lat.iloc[i], way_plots.end_node_lon.iloc[i]]], 
                                            weight=2, color='orange').add_to(m)
                        streamlit_folium.folium_static(m)
            
            # Display road risk levels around the address. 
            if chatout['Risk'] == True: 
                df_events_group9 = df_events.groupby('h3_9')['risk'].sum().reset_index()
                address_h3_9 = h3.latlng_to_cell(location.latitude, location.longitude, 9)
                extreme_high_risk = round(np.percentile(df_events_group9['risk'], 90), 1)
                high_risk = round(np.percentile(df_events_group9['risk'], 80), 1)
                medium_risk = round(np.percentile(df_events_group9['risk'], 70), 1)
                
                df_events_group9['medium_risk'] = (df_events_group9['risk']>=medium_risk) & (df_events_group9['risk']<high_risk)
                df_events_group9['high_risk'] = (df_events_group9['risk']>=high_risk) & (df_events_group9['risk']<extreme_high_risk)
                df_events_group9['extreme_high_risk'] = df_events_group9['risk'] >= extreme_high_risk
                st.write("Please check the road risk map.")

                # Define the map 
                with col2:
                    h3_sets = h3.grid_disk(address_h3_9, 1)
                    h3_value = address_h3_9
                    boundary = h3.cell_to_boundary(h3_value)
                    boundary = [(v[0], v[1]) for v in boundary]
                    h3_center = np.array(boundary).mean(axis=0).tolist()
                    m = folium.Map(location=h3_center, zoom_start=14, 
                                tiles=mapbox_url, attr='JBC', width=600, height=600)
                    folium.Marker(location=[location.latitude, location.longitude], 
                                  icon = folium.Icon(icon='location-dot', color='lightred', prefix='fa'), 
                                  popup=folium.Popup(chatout['Address'], max_width=300)).add_to(m)
                    for h3_value in h3_sets: 
                        boundary = h3.cell_to_boundary(h3_value)
                        boundary = [(v[0], v[1]) for v in boundary]
                        form = [boundary[i] for i in ConvexHull(boundary).vertices]
                        fg = folium.FeatureGroup(name="h3 shape")
                        h3_risk = df_events_group9[df_events_group9['h3_9'] == h3_value]
                        if h3_risk.empty: 
                            fill_color='#008080'
                        else: 
                            if h3_risk.extreme_high_risk.iloc[0] == True: 
                                fill_color='#8b0000' # dark red
                                pop_txt = 'extreme high risk region'
                            elif h3_risk.high_risk.iloc[0] == True:  
                                fill_color='purple'
                                pop_txt = 'high risk region'
                            elif h3_risk.medium_risk.iloc[0] == True: 
                                fill_color='orange'
                                pop_txt = 'medium risk region'
                            else:
                                fill_color='#008080' # teal
                                pop_txt = 'low risk region'
                        fg.add_child(
                            folium.vector_layers.Polygon(
                            locations=form,
                            color='grey',
                            fill_color=fill_color,
                            weight=2,
                            popup=folium.Popup(pop_txt, max_width=300),
                            )
                        )
                        m.add_child(fg)
                    streamlit_folium.folium_static(m)

        else: 
            st.write("No results found in OSM :cry:")
        
        
         



            # # Update the history string
            # st.session_state.chat_history = st.session_state.chat_history + f"Human: {chat}\nAssistant: {response['choices'][0]['text']}\n"

            # # Update the prompt history string
            # st.session_state.prompt_history = st.session_state.prompt_history + f"{chat} "

            # # Update the Overpass query. The query is enclosed by three backticks, denoting that is a code block.
            # # does the response contain a query? If so, update the query
            # if "```" in response["choices"][0]["text"]:
            #     st.session_state.overpass_query = response["choices"][0]["text"].split("```")[1]
            # else:
            #     st.session_state.overpass_query = None

            # # Define the query button in the left pane
            # with col2:

            #     if st.session_state.overpass_query:
            #         # Query the Overpass API
            #         response = query_overpass(st.session_state.overpass_query)

            #         # Check if the response is valid
            #         if "elements" in response and len(response["elements"]) > 0:
            #             # Create a new Folium map in the right pane
            #             m = folium.Map(location=[response["elements"][0]["lat"], response["elements"][0]["lon"]], zoom_start=11)

            #             # Add markers for each element in the response
            #             for element in response["elements"]:
            #                 if "lat" in element and "lon" in element:
            #                     folium.Marker([element["lat"], element["lon"]]).add_to(m)

            #             # Display the map
            #             streamlit_folium.folium_static(m)

            #             # If the request for summary of the API response is shorter than 1500 tokens,
            #             # use the Reader model to generate a response

            #             query_reader_prompt  = READER_TEMPLATE.format(prompt=st.session_state.prompt_history,
            #                                                           response=str(response))
            #             query_reader_prompt_tokens = len(ENC.encode(query_reader_prompt))
            #             if query_reader_prompt_tokens < 1500:

            #                 response = openai.Completion.create(
            #                     model="text-davinci-003",
            #                     prompt=query_reader_prompt,
            #                     temperature=0.5,
            #                     max_tokens=2047 - query_reader_prompt_tokens,
            #                     top_p=1,
            #                     frequency_penalty=0,
            #                     presence_penalty=0
            #                 )

            #                 # Display the response as pure text
            #                 st.write(response["choices"][0]["text"])
            #             else:
            #                 st.write("The API response is too long for me to read. Try asking for something slightly more specific! :smile:")
            #         else:
            #             st.write("No results found :cry:")
