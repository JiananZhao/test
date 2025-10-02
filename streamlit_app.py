import streamlit as st
import random
import time

st.title("Hello Streamlit-er 👋")
st.markdown(
    """ 
    This is a playground for you to try Streamlit and have fun. 

    **There's :rainbow[so much you can build!] **
    
    We prepared a few examples for you to get started. Just 
    click on the buttons above and discover what you can do 
    with Streamlit. 
    """
)

st.text("this is a text")

if st.button("Send balloons!"):
    st.balloons()

st.write("Streamlit loves LLMs! 🤖 [Build your own chat app](https://docs.streamlit.io/develop/tutorials/llms/build-conversational-apps) in minutes, then make it powerful by adding images, dataframes, or even input widgets to the chat.")
st.header("This is a header")
st.caption("Note that this demo app isn't actually connected to any LLMs. Those are expensive ;)")
st.code("This is a code section")

col1, col2 = st.columns(2)
with col1:
    st.text("Column 1")
with col2:
    st.text("Column 2")

with st.expander("More information"):
    st.text("This is some additional info that can be hidden.")
