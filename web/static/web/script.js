function setParam(name, value) {
    var l = window.location;

	/* build params */
    var params = {};
    var x = /(?:\??)([^=&?]+)=?([^&?]*)/g;
    var s = l.search;
    for(var r = x.exec(s); r; r = x.exec(s))
    {
        r[1] = decodeURIComponent(r[1]);
        if (!r[2]) r[2] = '%%';
        params[r[1]] = r[2];
    }

	/* set param */
    params[name] = encodeURIComponent(value);

	/* build search */
    var search = [];
    for(var i in params)
    {
        var p = encodeURIComponent(i);
        var v = params[i];
        if (v != '%%') p += '=' + v;
        search.push(p);
    }
    search = search.join('&');

	/* execute search */
    l.search = search;
}

//filtro para os genes

function verifyCheck(){
    const singleGene = document.getElementById('singleGene');
    const multipleGenes = document.getElementById('multipleGenes');

    if(window.location.href.includes("single_gene=1")){
        singleGene.checked = true;
        multipleGenes.checked = false;
    }
    else if(window.location.href.includes("multiple_genes=1")){
        singleGene.checked = false;
        multipleGenes.checked = true;
    }
    else{
        singleGene.checked = false;
        multipleGenes.checked = false;
    }
    singleGene.addEventListener('change',function(){
        if(singleGene.checked){
            multipleGenes.checked = false;
            let currentUrl = window.location.href;
            if (!currentUrl.includes("single_gene=1") && !currentUrl.includes("multiple_genes=1")) {
                let newUrl = currentUrl.includes("?") ? `${currentUrl}&single_gene=1` : `${currentUrl}?single_gene=1`;
                window.location.href = newUrl;
            }else if(!currentUrl.includes("single_gene=1") && currentUrl.includes("multiple_genes=1")) {
                currentUrl = currentUrl.replace(/(\?|&)multiple_genes=1/, "");
                newUrl = currentUrl.includes("?") ? `${currentUrl}&single_gene=1` : `${currentUrl}?single_gene=1`;
                window.location.href = newUrl;
            }
        }else{
            let newUrl = window.location.href.replace(/(\?|&)single_gene=1/, "");
            window.location.href = newUrl;
        }
    });

    multipleGenes.addEventListener('change',function(){
        if(multipleGenes.checked){
            singleGene.checked = false;
            let currentUrl = window.location.href;
            if (!currentUrl.includes("multiple_genes=1") && !currentUrl.includes("single_gene=1")) {
                let newUrl = currentUrl.includes("?") ? `${currentUrl}&multiple_genes=1` : `${currentUrl}?multiple_genes=1`;
                window.location.href = newUrl;
            }else if(!currentUrl.includes("multiples_genes=1") && currentUrl.includes("single_gene=1")) {
                currentUrl = currentUrl.replace(/(\?|&)single_gene=1/, "");
                newUrl = currentUrl.includes("?") ? `${currentUrl}&multiple_genes=1` : `${currentUrl}?multiple_genes=1`;
                window.location.href = newUrl;
            }
        }else{
            let newUrl = window.location.href.replace(/(\?|&)multiple_genes=1/, "");
            window.location.href = newUrl;
        }
    });
}
document.addEventListener('DOMContentLoaded', verifyCheck);