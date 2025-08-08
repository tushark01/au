import streamlit as st
from static.document_download import get_local_documents_path, list_local_documents, cleanup_local_documents

def display_local_document_manager(case_number: str):
    """
    Streamlit UI for managing, viewing, and downloading locally extracted PDF/image documents.
    Shows always after case number is entered, but disables UI if no files.
    """
    if not case_number or not case_number.strip():
        st.info("Enter a valid case number to view local documents.")
        return

    local_docs_path = get_local_documents_path(case_number.strip())
    session_key = f'show_docs_{case_number.strip()}'

    # Always show the expander
    with st.expander("🗂️ Local Document Manager", expanded=False):
        docs_exist = bool(local_docs_path and list_local_documents(local_docs_path)["total"])
        if docs_exist:
            st.success(f"Local documents available for case **{case_number}**.")
            col1, col2 = st.columns(2)

            button_text = "🙈 Hide Documents" if st.session_state.get(session_key, False) else "📄 Show Documents"
            if col1.button(button_text, use_container_width=True, key=f"show_{case_number}"):
                st.session_state[session_key] = not st.session_state.get(session_key, False)
            if col2.button("🗑️ Reset & Delete Local Documents", type="secondary", use_container_width=True, key=f"del_{case_number}"):
                if cleanup_local_documents(case_number.strip()):
                    st.toast(f"✅ Cleaned up local documents for case {case_number}.", icon="🧹")
                    if session_key in st.session_state:
                        del st.session_state[session_key]
                else:
                    st.error("Failed to clean up local documents.")

            # --- Only display files if toggle is ON ---
            if st.session_state.get(session_key, False):
                categorized_files = list_local_documents(local_docs_path)
                tab_titles, tabs = [], []
                if categorized_files["pdfs"]: tab_titles.append(f"📄 PDFs ({len(categorized_files['pdfs'])})")
                if categorized_files["images"]: tab_titles.append(f"🖼️ Images ({len(categorized_files['images'])})")
                if categorized_files["others"]: tab_titles.append(f"🗃️ Others ({len(categorized_files['others'])})")
                tabs = st.tabs(tab_titles)
                tab_index = 0

                # PDFs Tab: View inline & download
                if categorized_files["pdfs"]:
                    with tabs[tab_index]:
                        for file_path in categorized_files["pdfs"]:
                            st.markdown(f"**{file_path.name}**")
                            with open(file_path, "rb") as f:
                                file_bytes = f.read()
                            # View PDF inline
                            import base64
                            base64_pdf = base64.b64encode(file_bytes).decode("utf-8")
                            pdf_viewer = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800px"></iframe>'
                            st.markdown(pdf_viewer, unsafe_allow_html=True)
                            # Download button
                            st.download_button(label=f"Download {file_path.name}", data=file_bytes, file_name=file_path.name, mime="application/pdf")
                    tab_index += 1

                # Images Tab
                if categorized_files["images"]:
                    with tabs[tab_index]:
                        for file_path in categorized_files["images"]:
                            st.image(str(file_path), caption=file_path.name, use_container_width=True)
                    tab_index += 1

                # Others Tab
                if categorized_files["others"]:
                    with tabs[tab_index]:
                        for file_path in categorized_files["others"]:
                            st.markdown(f"**{file_path.name}**")
                            with open(file_path, "rb") as f:
                                st.download_button(f"Download {file_path.name}", f.read(), file_path.name)
        else:
            # If no docs, disable everything except a message
            st.info(f"No extracted files found for case: {case_number}.")
