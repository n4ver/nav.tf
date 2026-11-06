import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DataGrid from './DataGrid.vue'

describe('DataGrid', () => {
  const columns = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'kills', label: 'Kills', sortable: true, align: 'right', numeric: true },
  ]

  const rows = [
    { id: 'a', name: 'Alpha', kills: 5 },
    { id: 'b', name: 'Bravo', kills: 12 },
    { id: 'c', name: 'Charlie', kills: 8 },
  ]

  it('sorts rows when a sortable header is clicked', async () => {
    const wrapper = mount(DataGrid, {
      props: {
        rows,
        columns,
        rowKey: 'id',
        defaultSortKey: 'name',
        defaultSortDir: 'asc',
      },
    })

    const headers = wrapper.findAll('th')
    const killsHeader = headers.find((th) => th.text().includes('Kills'))
    expect(killsHeader).toBeTruthy()

    await killsHeader.get('button').trigger('click')
    let bodyText = wrapper.find('tbody').text()
    expect(bodyText.indexOf('Bravo')).toBeLessThan(bodyText.indexOf('Charlie'))
    expect(bodyText.indexOf('Charlie')).toBeLessThan(bodyText.indexOf('Alpha'))

    await killsHeader.get('button').trigger('click')
    bodyText = wrapper.find('tbody').text()
    expect(bodyText.indexOf('Alpha')).toBeLessThan(bodyText.indexOf('Charlie'))
    expect(bodyText.indexOf('Charlie')).toBeLessThan(bodyText.indexOf('Bravo'))
  })

  it('shows empty message when there are no rows', () => {
    const wrapper = mount(DataGrid, {
      props: {
        rows: [],
        columns,
        emptyMessage: 'Nothing here',
      },
    })
    expect(wrapper.text()).toContain('Nothing here')
  })

  it('greys out cells with zero values', () => {
    const wrapper = mount(DataGrid, {
      props: {
        rows: [
          { id: 'a', name: 'Alpha', kills: 0 },
          { id: 'b', name: 'Bravo', kills: 12 },
        ],
        columns,
        rowKey: 'id',
      },
    })

    const cells = wrapper.findAll('tbody td')
    const zeroCell = cells.find((td) => td.text() === '0')
    const nonZeroCell = cells.find((td) => td.text() === '12')

    expect(zeroCell?.classes()).toContain('text-ink-muted/50')
    expect(nonZeroCell?.classes()).not.toContain('text-ink-muted/50')
  })

  it('exposes sort state through aria-sort on sortable headers', async () => {
    // Arrange
    const wrapper = mount(DataGrid, {
      props: { rows, columns, rowKey: 'id', defaultSortKey: 'name', defaultSortDir: 'asc' },
    })
    const [nameHeader, killsHeader] = wrapper.findAll('th')

    // Act
    await killsHeader.get('button').trigger('click')

    // Assert
    expect(nameHeader.attributes('aria-sort')).toBe('none')
    expect(killsHeader.attributes('aria-sort')).toBe('descending')
  })

  it('makes clickable rows keyboard-activatable', async () => {
    // Arrange
    const onRowClick = vi.fn()
    const wrapper = mount(DataGrid, {
      props: { rows, columns, rowKey: 'id', defaultSortKey: 'name', defaultSortDir: 'asc', onRowClick },
    })
    const firstRow = wrapper.get('tbody tr')

    // Act
    await firstRow.trigger('keydown', { key: 'Enter' })

    // Assert
    expect(firstRow.attributes('tabindex')).toBe('0')
    expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({ id: 'a' }), 0)
  })

  it('does not make rows focusable without a click handler', () => {
    const wrapper = mount(DataGrid, { props: { rows, columns, rowKey: 'id' } })

    expect(wrapper.get('tbody tr').attributes('tabindex')).toBeUndefined()
  })
})
