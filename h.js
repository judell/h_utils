function embed_conversation(id) {
    element = document.getElementById(id);
    element.outerHTML = '<iframe height="300" src="https://hypothes.is/a/' + id + '"/>'
    return false;
}