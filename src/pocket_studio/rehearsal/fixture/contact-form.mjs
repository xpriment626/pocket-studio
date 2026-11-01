// Synthetic reference component, NOT Atlas UI. Real state owner and callback.
export function mountContactForm(root, service) {
  root.innerHTML = '<form><label>Name <input name="name" required></label><button type="submit">Add contact</button><p role="status"></p><ul aria-label="Contacts"></ul></form>'
  const form = root.querySelector('form'), status = root.querySelector('[role=status]')
  const state = { contacts: [], saving: false }
  form.addEventListener('submit', async event => {
    event.preventDefault()
    if (state.saving) return
    state.saving = true
    form.querySelector('button').disabled = true
    status.textContent = 'Saving'
    try {
      const saved = await service.create({ name: form.elements.name.value })
      state.contacts.push(saved)
      const row = document.createElement('li'); row.textContent = saved.name
      root.querySelector('ul').append(row)
      status.textContent = 'Contact added'
    } catch { status.textContent = 'Could not save contact' }
    finally { state.saving = false; form.querySelector('button').disabled = false }
  })
  return state
}
