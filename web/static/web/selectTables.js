function verifCheck(){
    // Protein
    function elementByID(id){
        return document.getElementById(id);
    }
    function elementsByClass(className){
        return document.getElementsByClassName(className);
    }

    function toggleVisibility(checkbox, colummn, filter, tdElement,thElement){
        const displayStyle = checkbox.checked ? '' : 'none';

        colummn.style.display = displayStyle;
        filter.style.display = displayStyle;
        thElement.style.display = displayStyle;
        for(let i = 0; i < tdElement.length;i++){
            tdElement[i].style.display = displayStyle;
        }
    }

    // Protein ID
    const proteinID = [
        elementByID('protein-id-checkbox'),
        elementByID('protein-id'),
        elementByID('filter-protein-id'),
        elementsByClass('protein-id-td'),
        elementByID('protein-id-th')
    ]

    // Protein Mutation
    const proteinMutation = [
        elementByID('protein-mutation-checkbox'),
        elementByID('protein-mutation'),
        elementByID('filter-protein-mutation'),
        elementsByClass('protein-mutation-td'),
        elementByID('protein-mutation-th')
    ]

    // Genomic ID
    const genomicID = [
        elementByID('genomic-id-checkbox'),
        elementByID('genomic-id'),
        elementByID('filter-genomic-id'),
        elementsByClass('genomic-id-td'),
        elementByID('genomic-id-th')
    ]

    // Genomic Mutation
    const genomicMutation = [
        elementByID('genomic-mutation-checkbox'),
        elementByID('genomic-mutation'),
        elementByID('filter-genomic-mutation'),
        elementsByClass('genomic-mutation-td'),
        elementByID('genomic-mutation-th')
    ]

    // mRNA ID
    const mrnaID = [
        elementByID('mrna-id-checkbox'),
        elementByID('mrna-id'),
        elementByID('filter-mrna-id'),
        elementsByClass('mrna-id-td'),
        elementByID('mrna-id-th')
    ]

    // mRNA Mutation
    const mrnaMutation = [
        elementByID('mrna-mutation-checkbox'),
        elementByID('mrna-mutation'),
        elementByID('filter-mrna-mutation'),
        elementsByClass('mrna-mutation-td'),
        elementByID('mrna-mutation-th')
    ]


    proteinID[0].addEventListener('change', function() {
        toggleVisibility(proteinID[0],proteinID[1],proteinID[2],proteinID[3],proteinID[4]);
    });

    proteinMutation[0].addEventListener('change', function(){
        toggleVisibility(proteinMutation[0],proteinMutation[1],proteinMutation[2],proteinMutation[3],proteinMutation[4]);
    });

    genomicID[0].addEventListener('change', function(){
        toggleVisibility(genomicID[0],genomicID[1],genomicID[2],genomicID[3],genomicID[4]);
    });

    genomicMutation[0].addEventListener('change', function(){
        toggleVisibility(genomicMutation[0],genomicMutation[1],genomicMutation[2],genomicMutation[3],genomicMutation[4]);
    });

    mrnaID[0].addEventListener('change', function(){
        toggleVisibility(mrnaID[0],mrnaID[1],mrnaID[2],mrnaID[3],mrnaID[4]);
    });

    mrnaMutation[0].addEventListener('change', function(){
        toggleVisibility(mrnaMutation[0],mrnaMutation[1],mrnaMutation[2],mrnaMutation[3],mrnaMutation[4]);
    });
  }


  document.addEventListener('DOMContentLoaded', verifCheck);