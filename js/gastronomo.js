M.AutoInit();

document.addEventListener('DOMContentLoaded', function() {
    var elems = document.querySelectorAll('.chips');
    var instances = M.Chips.init(elems, { onChipAdd: changeColor });

});

// Color rojo en vez del azul por defecto
function changeColor() {
    document.querySelectorAll('.chip').forEach(chip => {
        chip.classList.add('red');
    })
}

document.addEventListener('DOMContentLoaded', function() {
    var elems = document.querySelectorAll('select');
    var instances = M.FormSelect.init(elems, options);
});

// Or with jQuery

$(document).ready(function() {
    $('select').formSelect();
});