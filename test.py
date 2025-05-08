import os
import json
import time
import logging
import streamlit as st
from dotenv import load_dotenv
from pprint import pprint
import pandas as pd
import io

from sl.utils import agent_response, gen_stream, gen_worker_list, display_workers, get_model_provider, load_secrets, gen_agent
load_secrets()

from arklex.utils.utils import init_logger
from arklex.orchestrator.orchestrator import AgentOrg
from arklex.utils.model_config import MODEL
from arklex.utils.model_provider_config import LLM_PROVIDERS
from arklex.env.env import Env
import create as gen

from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
from bs4 import BeautifulSoup

#st.session_state.INPUT_DIR = "./agent/cs_test"
st.session_state.gen_counter = 0
st.session_state.custom_keys = []
st.session_state.tmp_api_name = ""
st.session_state.tmp_api_key = ""
st.session_state.tmp_api_info = {
    "api_name": "",
    "api_key": "",
    "docs_link": "",
    "api_desc": ""
}
MODEL["model_type_or_path"] = "gpt-4.1"
LOG_LEVEL = "WARNING"
WORKER_PREFIX = "assistant"
USER_PREFIX = "user"
LOGO_FULL = "./assets/ryaa_logo.svg"
LOGO_MINI = "./assets/ryaa_mini.svg"
LOGO_MICRO = "./assets/ryaa_micro.svg"
ICON_HUMAN = ":material/face:"
BLANK = "./assets/blank.svg"
models = (
            "gpt-4.1", 
            "gpt-4.1-mini", 
            "gpt-4.1-nano",
            "gemini-2.0-flash",
            "gemini-2.5-flash-preview-04-17",
            "gemini-2.5-pro-preview-03-25",
            "claude-3-7-sonnet-20250219"
        )
@st.dialog("Add in API functionality")
def new_agent_config():
    api_info = st.session_state.tmp_api_info
    
    api_name = st.text_input("API Key Name")
    api_key = st.text_input("API Key")
    docs_link = st.text_input("API Documentation Source", placeholder="enter api doc link...")
    api_desc = st.text_input("API Docs Description", placeholder="API docs for...")

    if st.button("Submit"):
        api_info["api_name"] = api_name
        api_info["api_key"] = api_key
        api_info["docs_link"] = docs_link
        api_info["api_desc"] = api_desc
        st.session_state.tmp_api_info = api_info
        st.rerun()

def get_website_content(url):
    driver = None
    try:
        st.write("DEBUG: Setting up Chrome options...")
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1200')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        st.write("DEBUG: Initializing Chrome driver...")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.set_page_load_timeout(15)
        
        st.write(f"DEBUG: Loading URL: {url}")
        driver.get(url)
        st.write("DEBUG: Page loaded")
        
        html_doc = driver.page_source
        st.write("DEBUG: Got page source, length: " + str(len(html_doc)))
        
        # Close the driver BEFORE processing content
        st.write("DEBUG: Closing driver...")
        driver.quit()
        driver = None
        st.write("DEBUG: Driver closed")
        
        # Process content after driver is closed
        soup = BeautifulSoup(html_doc, "html.parser")
        text = soup.get_text()
        st.write(f"DEBUG: Extracted text, length: {len(text)}")
        return text
    except Exception as e:
        st.write(f"DEBUG: Error: {str(e)}")
        return f"Error: {str(e)}"
    finally:
        if driver is not None:
            st.write("DEBUG: Quitting driver in finally block")
            try:
                driver.quit()
                st.write("DEBUG: Successfully quit driver in finally block")
            except Exception as e:
                st.write(f"DEBUG: Error quitting driver in finally block: {e}")
def blank_slate():
    st.session_state.history = []
    st.session_state.params = {}
    st.session_state.workers = []
    st.session_state.empty = True

    # derived from Arklex, grab configured start response from config
    #for node in config["nodes"]:
    #    if node[1].get("type", "") == "start":
    #        start_message = node[1]["attribute"]["value"]
    #        break

    #st.session_state.history.append({"role": WORKER_PREFIX, "content": start_message})
    #st.session_state.workers.append("")  # ensure worker list maintains equivalent index to history

# env, config derived from Arklex, "run.py" file


# Streamlit GUI
st.set_page_config(
    page_title="Ryaa",
    page_icon=LOGO_MICRO
)
st.logo(
    LOGO_MINI,
    size="large"
)

logo = st.empty()
# initialization or reset button
if "history" not in st.session_state:
    blank_slate()
    
    logo.image(
        LOGO_FULL,
        width=300
    )
    

with st.sidebar:
    voice = st.toggle("Voice")
    debug = st.toggle("Debug Mode", value=False)
    config_option = st.selectbox(
        "Agent",
        ("./agent/api_assistant",
         "./agent/api_assistant2",
         "./agent/api_agent0",
         "./agent/cs_test",
         "./agent/cs_test2")
    )
    st.session_state.INPUT_DIR=config_option
    if st.button("reload config"):
        os.environ["DATA_DIR"] = st.session_state.INPUT_DIR
        st.write(os.environ["DATA_DIR"])
        config = json.load(open(os.path.join(st.session_state.INPUT_DIR, "taskgraph.json")))
        env = Env(
            tools = config.get("tools", []),
            workers = config.get("workers", []),
            slotsfillapi = config["slotfillapi"]
        )
    
    model_option = st.selectbox(
        "Model", models, 
        help="""
        *gpt-4.1* - Slowest, Most Intelligent  \n
        *gpt-4.1-mini* - Faster, Less Intelligent  \n
        *gpt-4.1-nano* - Fastest, Least Intelligent
        """
    )
    MODEL["model_type_or_path"] = model_option
    MODEL["llm_provider"] = get_model_provider(model_option)
    # generate reset button w/ loader to the right
    col1, col2 = st.columns([0.5,2], vertical_alignment='center')
    with col1:
        if st.button(":material/refresh:", type="primary", help="Reset Chat"):
            with col2:
                with st.spinner(" "):
                    blank_slate()
                    time.sleep(0.75)

    config_path = st.text_input("Config Location", "./configs/api_test.json")
    #rag_link = st.text_input("New API Document Source", placeholder="enter api doc link...")
    #rag_desc = st.text_area("New API Description (Optional)", placeholder="API docs for...")
    #api_key_name = st.text_input("API Key Name")
    #api_key_val = st.text_input("API Key Value")
    if st.button("Create New Agent"):
        new_agent_config()
        st.write(st.session_state.tmp_api_info)
        with st.status("Creating New Agent..."):
            st.session_state.custom_keys.append(st.session_state.tmp_api_info["api_name"])
            os.environ[st.session_state.tmp_api_info["api_name"]] = st.session_state.tmp_api_info["api_key"]
            st.write("Opening config...")
            with open(config_path, "r") as file:
                agent_config = json.load(file)

            rag_doc = {
                "source": st.session_state.tmp_api_info["docs_link"],
                "desc": st.session_state.tmp_api_info["api_desc"],
                "num": 1
            }
            agent_config["rag_docs"].append(rag_doc)
            st.write("Writing to config...")
            with open(config_path, "w") as file:
                json.dump(agent_config, file, indent=2)
            #st.success(f"New Doc Added {rag_link}")
            st.write("Generating new agent...")
            gen_agent(config_path,model_option, get_model_provider(model_option))
            st.write("Clearing chat...")
            st.session_state.tmp_api_info = {key: None for key in st.session_state.tmp_api_info}
            st.session_state.INPUT_DIR = config_option
            blank_slate()
            #st.rerun()

os.environ["DATA_DIR"] = st.session_state.INPUT_DIR
config = json.load(open(os.path.join(st.session_state.INPUT_DIR, "taskgraph.json")))
env = Env(
    tools = config.get("tools", []),
    workers = config.get("workers", []),
    slotsfillapi = config["slotfillapi"]
)

# Chat History Rendering
if debug: 
    st.write(st.session_state.workers)
    st.write(os.listdir("./agent"))
    
    #st.write(st.session_state.INPUT_DIR)
    
for message, workers in zip(st.session_state.history, st.session_state.workers):
    history_icon = LOGO_MICRO if message["role"] == "assistant" else ICON_HUMAN
    with st.chat_message(message["role"], avatar=history_icon):
        if debug and "memory" in st.session_state.params:
            st.write(st.session_state.params["memory"]["trajectory"])
        st.write(message["content"])
        display_workers(workers)

# Handle User Input & Response
if prompt := st.chat_input("Ask Ryaa"):
    st.session_state.empty = False
    
    with st.chat_message("user", avatar=ICON_HUMAN):
        st.write(prompt)
        logo.empty()
    st.session_state.history.append({"role": USER_PREFIX, "content": prompt})
    st.session_state.workers.append("")    
    with st.spinner("Loading..."):
        output, st.session_state.params, hitl = agent_response(st.session_state.INPUT_DIR, st.session_state.history, 
                                                               prompt, st.session_state.params, env)
        
        workers, sources = gen_worker_list(st.session_state.params) 

    with st.chat_message("assistant", avatar=LOGO_MICRO):
        if debug: 
            st.write(st.session_state.params["memory"]["trajectory"]) # 
        st.write(output)
        #st.write_stream(gen_stream(output, delay=0.0001))
        detail_col1, detail_col2 = st.columns([0.5,2], vertical_alignment='center')
        with detail_col1:
            display_workers(workers)
            if "FaissRAGWorker" in workers:
                with detail_col2:
                    with st.expander("Sources Used"):
                        for source in sources:
                            st.write(source)

    st.session_state.history.append({"role": WORKER_PREFIX, "content": output})
    st.session_state.workers.append(workers)


    #st.rerun()