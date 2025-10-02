import streamlit as st
import random
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

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

# Matplotlib Example
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [10, 20, 30])
st.pyplot(fig)

st.sidebar.title("Sidebar")
number = st.sidebar.slider("Select a number", 0, 100)
st.write(f"Selected number: {number}")
