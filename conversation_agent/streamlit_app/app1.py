import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(layout="wide", page_title="Docs Assistant")

# The native Watsonx Web Chat HTML and JS
html_code = """
<!DOCTYPE html>
<html>
<head>
<style>
  /* Force the container to take the full frame */
  html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    overflow: hidden;
    background-color: #f4f4f4;
  }
</style>
</head>
<body>
<script>
  window.wxOConfiguration = {
    orchestrationID: "20260720-1900-4735-1039-0adb5c904e27_20260720-1901-4104-3034-128794311de0",
    hostURL: "https://ap-south-1.dl.watson-orchestrate.ibm.com",
    rootElementID: "root",
    chatOptions: {
        agentId: "9c0bb3a2-c97b-4e46-9237-f69c6d29755b", 
        agentEnvironmentId: "6c393589-3791-4feb-bb62-7982c6a22e60",
    }
  };
  setTimeout(function () {
    const script = document.createElement('script');
    script.src = `${window.wxOConfiguration.hostURL}/wxochat/wxoLoader.js?embed=true`;
    script.addEventListener('load', function () {
        wxoLoader.init();
    });
    document.head.appendChild(script);
  }, 0);                     
</script>
</body>
</html>
"""

# Render the HTML block in Streamlit, taking up the full width/height
st.iframe (html_code, height=800, width=800)