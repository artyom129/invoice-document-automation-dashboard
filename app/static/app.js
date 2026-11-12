// Make a whole table row open its invoice. The link inside the row still works on its own.
document.querySelectorAll('tr[data-href]').forEach((row) =>
  row.addEventListener('click', (event) => {
    if (event.target.closest('a, button')) return;
    window.location.href = row.dataset.href;
  }));

// Show that something is running while a batch uploads, since extraction can take a moment.
document.querySelectorAll('form').forEach((form) =>
  form.addEventListener('submit', (event) => {
    const button = event.submitter;
    if (!button) return;
    button.classList.add('busy');
    setTimeout(() => { button.disabled = true; }, 0);
  }));
