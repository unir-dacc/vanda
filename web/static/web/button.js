document.addEventListener("DOMContentLoaded", function() {
  const button1 = document.getElementById("show-snp");
  const button2 = document.getElementById("show-keywords");
  
  // Define o estilo de botão clicado para o botão 1 ao carregar a página
  button2.classList.add("clicked");
  
  button1.addEventListener("click", function() {
    button1.classList.add("clicked");
    button2.classList.remove("clicked");
  });
  
  button2.addEventListener("click", function() {
    button2.classList.add("clicked");
    button1.classList.remove("clicked");
  });
});

function showSNP(){
  document.getElementById("snp-container").style.display = "block";
  document.getElementById("keywords-container").style.display = "none";
}
function showKeywords(){
  document.getElementById("snp-container").style.display = "none";
  document.getElementById("keywords-container").style.display = "block";
}