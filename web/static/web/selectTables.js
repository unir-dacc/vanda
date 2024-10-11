function verifCheck(){
    // Protein
    const protein = document.getElementById('protein-checkbox');
    var protein_column = document.getElementById('protein-column');
    var protein_filter = document.getElementById('filter-np');
    var protein_td = document.getElementsByClassName('protein-td');
    var protein_th = document.getElementById('protein-th');
    // Genomic
    const genomic = document.getElementById('genomic-checkbox');
    var genomic_column = document.getElementById('genomic-column');
    var genomic_filter = document.getElementById('filter-nc');
    var genomic_td = document.getElementsByClassName('genomic-td');
    var genomic_th = document.getElementById('genomic-th');

    protein.addEventListener('change', function() {
        if (protein.checked) {
            // Ocultar as variáveis relacionadas à proteína
            protein_column.style.display = '';
            protein_filter.style.display = '';
            for (let i = 0; i < protein_td.length; i++) {
                protein_td[i].style.display = '';
            }
            protein_th.style.display = '';
        } else {
            // Exibir as variáveis relacionadas à proteína
            protein_column.style.display = 'none';
            protein_filter.style.display = 'none';
            for (let i = 0; i < protein_td.length; i++) {
                protein_td[i].style.display = 'none';
            }
            protein_th.style.display = 'none';
        }
    });
    genomic.addEventListener('change', function() {
        if (genomic.checked) {
            // Ocultar as variáveis relacionadas à proteína
            genomic_column.style.display = '';
            genomic_filter.style.display = '';
            for (let i = 0; i < genomic_td.length; i++) {
                genomic_td[i].style.display = '';
            }
            genomic_th.style.display = '';
        } else {
            // Exibir as variáveis relacionadas à proteína
            genomic_column.style.display = 'none';
            genomic_filter.style.display = 'none';
            for (let i = 0; i < genomic_td.length; i++) {
                genomic_td[i].style.display = 'none';
            }
            genomic_th.style.display = 'none';
        }
    });
  }


  document.addEventListener('DOMContentLoaded', verifCheck);